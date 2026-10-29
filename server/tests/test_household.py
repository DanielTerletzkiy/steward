"""Locations, pieces per pack and bottle deposit on receipts, and importing eBons from email."""

from __future__ import annotations

import imaplib
import itertools
from datetime import date, datetime, timezone
from email.message import EmailMessage

import pytest

from steward_server.db import Database
from steward_server.deposit import bottles_per_deposit, line_bottles, pieces_from_name
from steward_server.events import EventHub
from steward_server.models import Receipt, ReceiptLine, StockEntry
from steward_server.schemas import (
    EntryPatch,
    LineMatchIn,
    LocationIn,
    LocationPatch,
    ProductIn,
    ProductOut,
    ShoppingItemIn,
    ShoppingItemPatch,
    TaskIn,
    TaskPatch,
)
from steward_server.services import Invalid, NotFound, catalog, mail, receipts, scan, shopping, stock, tasks


@pytest.fixture
async def session(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.create_all()
    async with db.sessions() as s:
        yield s
    await db.dispose()


@pytest.fixture
def hub():
    return EventHub()


# --- locations --------------------------------------------------------------


async def test_locations_are_managed_and_lots_move(session, hub):
    pantry = await catalog.create_location(session, hub, LocationIn(name="Pantry"))
    freezer = await catalog.create_location(session, hub, LocationIn(name="Freezer", is_freezer=True))
    with pytest.raises(Invalid):
        await catalog.create_location(session, hub, LocationIn(name=" pantry "))
    with pytest.raises(Invalid):
        await catalog.update_location(session, hub, freezer.id, LocationPatch(name="PANTRY"))

    renamed = await catalog.update_location(session, hub, pantry.id, LocationPatch(name="Larder"))
    assert renamed.name == "Larder"

    bread = await catalog.create_product(session, hub, ProductIn(name="Bread", location_id=pantry.id))
    entry = await stock.purchase(session, hub, bread.id, 2)
    assert entry.location_id == pantry.id
    moved = await stock.move_entry(session, hub, entry.id, freezer.id)
    assert moved.location_id == freezer.id

    await catalog.delete_location(session, hub, freezer.id)
    await session.refresh(entry)
    assert entry.location_id is None
    await catalog.delete_location(session, hub, pantry.id)
    await session.refresh(bread)
    assert bread.location_id is None
    assert await catalog.list_locations(session) == []


# --- deposit and packs ------------------------------------------------------------


def test_bottles_per_deposit():
    assert bottles_per_deposit(0.25) == 1
    assert bottles_per_deposit(1.50) == 6  # one-way 6-pack
    assert bottles_per_deposit(3.10) == 20  # crate: 1,50 + 20 x 0,08
    assert bottles_per_deposit(0.15) == 1
    assert bottles_per_deposit(0.07) is None
    assert line_bottles("deposit", "PFAND 1,50 EURO", 2, None, 3.0) == 12
    assert line_bottles("deposit", "PFAND 0,25 EURO", 2, 0.25, 0.5) == 2
    assert line_bottles("deposit_return", "LEERGUT EINWEG", 26, 0.25, -6.5) == 26
    assert line_bottles("item", "ZERO LEMON", 1, None, 8.94) is None


def test_pieces_from_name():
    assert pieces_from_name("COLA 6X1,5L") == 6
    assert pieces_from_name("JOGHURT 4 X 150G") == 4
    assert pieces_from_name("ZERO LEMON") is None
    assert pieces_from_name("MILCH 1,5% 1X1L") is None


_receipt_ids = itertools.count(1)


def _receipt(lines: list[tuple[str, float, float, float | None]], at: datetime | None = None) -> Receipt:
    receipt = Receipt(
        external_id=f"test-{next(_receipt_ids)}", chain="REWE", store="REWE", at=at or datetime(2026, 10, 1, 10, tzinfo=timezone.utc),
        total=sum(line[2] for line in lines), source="test",
    )  # fmt: skip
    for idx, (text, qty, total, unit_price) in enumerate(lines):
        receipt.lines.append(
            ReceiptLine(idx=idx, raw_text=text, qty=qty, total=total, unit_price=unit_price, kind=receipts.classify(text))
        )
    return receipt


async def test_packs_are_counted_from_the_deposit_and_stocked_as_pieces(session, hub):
    receipt = _receipt(
        [
            ("ZERO LEMON", 1, 8.94, None),
            ("PFAND 1,50 EURO", 1, 1.50, None),
            ("ZERO CHERRY", 2, 1.58, 0.79),
            ("PFAND 0,25 EURO", 2, 0.50, 0.25),
            ("JOGHURT 4X150G", 1, 1.99, None),
            ("BROT", 1, 2.49, None),
            ("LEERGUT EINWEG", 4, -1.00, 0.25),
        ]
    )
    session.add(receipt)
    await session.flush()
    await receipts.fill_pieces(session, receipt.lines)
    pieces = {line.raw_text: (line.pieces, line.pieces_source) for line in receipt.lines if line.kind == "item"}
    assert pieces == {
        "ZERO LEMON": (6, "deposit"),
        "ZERO CHERRY": (1, "deposit"),
        "JOGHURT 4X150G": (4, "name"),
        "BROT": (1, None),
    }

    lemon = await catalog.create_product(session, hub, ProductIn(name="Zero Lemon"))
    for line in receipt.lines:
        if line.raw_text == "ZERO LEMON":
            line.product_id = lemon.id
    await session.commit()
    await receipts.stock_receipt(session, hub, receipt.id)
    entry = (await stock.stock_overview(session))[0]
    assert entry.amount == 6
    assert entry.entries[0].unit_price == pytest.approx(1.49)

    spending = await receipts.spending(session)
    assert spending["deposit_bottles"] == {"bought": 8, "returned": 4, "open": 4}
    assert spending["deposit_balance"] == 1.0


async def test_corrected_pieces_are_learned_per_price(session, hub):
    first = _receipt([("SPRUDEL", 1, 4.99, None), ("SPRUDEL", 1, 0.59, None)])
    second = _receipt([("SPRUDEL", 1, 4.99, None)])
    session.add_all([first, second])
    await session.flush()
    await receipts.fill_pieces(session, first.lines + second.lines)
    pack = next(line for line in first.lines if line.total == 4.99)

    await receipts.set_line_pieces(session, hub, first.id, pack.id, 12)
    single = next(line for line in first.lines if line.total == 0.59)
    assert (pack.pieces, pack.pieces_source) == (12, "manual")
    assert single.pieces == 1  # same text, other price
    assert (second.lines[0].pieces, second.lines[0].pieces_source) == (12, "learned")

    # New receipts pick it up too.
    third = _receipt([("SPRUDEL", 2, 9.98, 4.99)])
    session.add(third)
    await session.flush()
    await receipts.fill_pieces(session, third.lines)
    assert third.lines[0].pieces == 12


async def test_backfill_fills_old_lines(session, hub):
    receipt = _receipt([("ZERO LEMON", 1, 8.94, None), ("PFAND 1,50 EURO", 1, 1.50, None)])
    session.add(receipt)
    await session.commit()
    assert receipt.lines[0].pieces is None
    await receipts.backfill_pieces(session)
    assert receipt.lines[0].pieces == 6


# --- receipt texts -------------------------------------------------------------------


async def test_product_receipt_texts_are_edited(session, hub):
    soap = await catalog.create_product(session, hub, ProductIn(name="Cream soap"))
    bread = await catalog.create_product(session, hub, ProductIn(name="Bread"))
    await receipts.set_product_aliases(session, hub, bread.id, ["CREMESEIFE"])
    receipt = _receipt([("CREMESEIFE", 1, 0.65, None), ("SEIFE  flüssig", 1, 1.29, None), ("XYZ", 1, 1.0, None)])
    session.add(receipt)
    await session.flush()
    for line in receipt.lines:
        await receipts.match_line(session, line)
    await session.commit()
    assert receipt.lines[0].product_id == bread.id

    # Adding texts normalizes them; a text another product had moves over, and open lines follow it.
    result = await receipts.set_product_aliases(session, hub, soap.id, ["cremeseife", "Seife flüssig", " ", "CREMESEIFE"])
    assert [a.normalized for a in result.aliases] == ["CREMESEIFE", "SEIFE FLUESSIG"]
    assert [(m.text, m.product_name) for m in result.moved] == [("CREMESEIFE", "Bread")]
    await session.refresh(receipt, ["lines"])
    assert [(line.product_id, line.method) for line in receipt.lines[:2]] == [(soap.id, "alias"), (soap.id, "alias")]

    # Removing a text frees its lines again; texts confirmed by hand stay.
    await receipts.set_line_product(session, hub, receipt.id, receipt.lines[2].id, LineMatchIn(product_id=soap.id))
    result = await receipts.set_product_aliases(session, hub, soap.id, ["SEIFE FLUESSIG"])
    assert [a.normalized for a in result.aliases] == ["SEIFE FLUESSIG"]
    await session.refresh(receipt, ["lines"])
    first, _, third = receipt.lines
    assert first.confirmed is False and first.method != "alias"
    assert (third.product_id, third.confirmed) == (soap.id, True)
    assert {a.normalized for a in await receipts.list_aliases(session)} == {"SEIFE FLUESSIG"}

    # Stocked receipts are history and keep their products.
    await receipts.set_product_aliases(session, hub, bread.id, ["SEIFE FLUESSIG"])
    receipt.stocked = True
    await session.commit()
    await receipts.set_product_aliases(session, hub, bread.id, [])
    await session.refresh(receipt, ["lines"])
    assert receipt.lines[1].product_id == bread.id


# --- editing what was created ------------------------------------------------------


async def test_stock_entries_are_corrected_and_undone(session, hub):
    milk = await catalog.create_product(session, hub, ProductIn(name="Milk", min_stock=2))
    entry = await stock.purchase(session, hub, milk.id, 3, unit_price=1.1)
    await stock.edit_entry(session, hub, entry.id, EntryPatch(amount=1, due_date=date(2026, 11, 20), unit_price=0.99))
    assert (entry.amount, entry.due_date, entry.unit_price) == (1, date(2026, 11, 20), 0.99)
    correction = (await stock.journal(session))[0]
    assert (correction.type, correction.amount) == ("correct", -2)
    default = await shopping.default_list(session)
    assert any(i.product_id == milk.id for i in await shopping.items(session, default.id))

    await stock.edit_entry(session, hub, entry.id, EntryPatch(due_date=None))
    assert (entry.amount, entry.due_date) == (1, None)
    await stock.undo(session, hub, correction.id)
    await session.refresh(entry)
    assert entry.amount == 3
    with pytest.raises(NotFound):
        await stock.edit_entry(session, hub, 999, EntryPatch(amount=1))


async def test_tasks_and_shopping_items_are_edited(session, hub):
    task = await tasks.create_task(session, hub, TaskIn(name="Call the landlord", due_date=date(2026, 11, 3)))
    task = await tasks.update_task(session, hub, task.id, TaskPatch(name="Call landlord", due_date=None, notes="about the heating"))
    assert (task.name, task.due_date, task.notes, task.category) == ("Call landlord", None, "about the heating", "General")
    with pytest.raises(Invalid):
        await tasks.update_task(session, hub, task.id, TaskPatch(name=" "))

    default = await shopping.default_list(session)
    item = await shopping.add_item(session, hub, default.id, ShoppingItemIn(text="Apples"))
    item = await shopping.update_item(session, hub, item.id, ShoppingItemPatch(text="Pears", amount=3, note="ripe"))
    assert (item.text, item.amount, item.note, item.done) == ("Pears", 3, "ripe", False)
    with pytest.raises(Invalid):
        await shopping.update_item(session, hub, item.id, ShoppingItemPatch(amount=0))


async def test_barcodes_are_removed_and_receipts_deleted(session, hub):
    bread = await catalog.create_product(session, hub, ProductIn(name="Bread"))
    product = await scan.add_barcode(session, hub, bread.id, "4001234567890")
    assert [b.code for b in ProductOut.model_validate(product).barcodes] == ["4001234567890"]
    product = await scan.remove_barcode(session, hub, bread.id, "4001234567890")
    assert ProductOut.model_validate(product).barcodes == []
    with pytest.raises(NotFound):
        await scan.remove_barcode(session, hub, bread.id, "4001234567890")

    receipt = _receipt([("BROT", 1, 2.49, None)])
    receipt.lines[0].product_id = bread.id
    session.add(receipt)
    await session.commit()
    await receipts.stock_receipt(session, hub, receipt.id)
    await receipts.delete_receipt(session, hub, receipt.id)
    assert await receipts.list_receipts(session) == []
    assert (await stock.stock_overview(session))[0].amount == 1  # the stock stays


# --- email import -------------------------------------------------------------------


def _mail(pdf: bytes | None, sender: str = "REWE eBon <ebon@mailing.rewe.de>") -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["Subject"] = "Dein REWE eBon"
    message.set_content("Danke für deinen Einkauf.")
    if pdf is not None:
        message.add_attachment(pdf, maintype="application", subtype="pdf", filename="eBon.pdf")
    return message.as_bytes()


def test_pdf_attachments():
    assert mail.pdf_attachments(_mail(b"%PDF-1.4 receipt")) == [b"%PDF-1.4 receipt"]
    assert mail.pdf_attachments(_mail(None)) == []


class FakeIMAP:
    """Just enough of imaplib.IMAP4_SSL: one folder with numbered mails."""

    mails: dict[int, bytes] = {}
    seen: set[int] = set()
    password = "app-password"

    def __init__(self, host, port, timeout=None):
        self.readonly = True

    def login(self, user, password):
        if password != self.password:
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials")
        return "OK", [b"ok"]

    def logout(self):
        return "BYE", [b""]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasChildren \\Noselect) "/" "[Gmail]"']

    def select(self, mailbox, readonly=False):
        self.readonly = readonly
        return ("OK", [str(len(self.mails)).encode()]) if mailbox == '"INBOX"' else ("NO", [b"no such folder"])

    def response(self, code):
        return code, [b"7"]

    def uid(self, command, *args):
        if command == "SEARCH":
            args = [a for a in args if a is not None]
            uids = sorted(self.mails)
            if args[0] == "UID":
                low = int(args[1].split(":")[0])
                uids = [u for u in uids if u >= low] or uids[-1:]
            return "OK", [" ".join(str(u) for u in uids).encode()]
        if command == "FETCH":
            uid = int(args[0])
            return "OK", [(f"{uid} (UID {uid} BODY[] {{1}}".encode(), self.mails[uid]), b")"]
        if command == "STORE":
            assert not self.readonly
            self.seen.update(int(u) for u in args[0].split(","))
            return "OK", [b""]
        raise AssertionError(command)


async def test_email_import(session, hub, monkeypatch):
    FakeIMAP.mails = {3: _mail(b"%PDF-receipt-a"), 4: _mail(None), 5: _mail(b"%PDF-not-an-ebon")}
    FakeIMAP.seen = set()
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeIMAP)

    async def fake_import(session, hub, pdf, *, source="upload"):
        if b"not-an-ebon" in pdf:
            raise Invalid("Could not read this eBon")
        receipt = _receipt([("BROT", 1, 2.49, None)])
        receipt.external_id, receipt.source = receipts.hashlib.sha256(pdf).hexdigest(), source
        session.add(receipt)
        await session.commit()
        return receipt

    monkeypatch.setattr(receipts, "import_ebon", fake_import)

    with pytest.raises(Invalid):
        await mail.save_config(session, hub, {"enabled": True, "username": "me@gmail.com"})
    # Google shows app passwords in groups; the spaces are dropped.
    saved = await mail.save_config(
        session, hub, {"enabled": True, "username": "me@gmail.com", "password": "app-pass word", "mark_read": True}
    )
    assert "password" not in saved and saved["password_set"]
    assert (await mail.load_config(session))["password"] == "app-password"
    checked = await mail.test(session)
    assert checked == {"ok": True, "folders": ["INBOX"], "matches": 3}

    first = await mail.run(session, hub)
    assert (first["mails"], first["imported"], first["skipped"], first["known"]) == (3, 1, 1, 0)
    assert FakeIMAP.seen == {3}
    config = await mail.load_config(session)
    assert config["state"] == {"uidvalidity": 7, "last_uid": 5}

    # Nothing new: the newest mail is not read again.
    again = await mail.run(session, hub)
    assert again["mails"] == 0
    assert await mail.run_if_due(session, hub) is None  # just ran

    FakeIMAP.mails[6] = _mail(b"%PDF-receipt-b")
    FakeIMAP.mails[7] = _mail(b"%PDF-receipt-a")  # the same eBon forwarded again
    third = await mail.run(session, hub)
    assert (third["imported"], third["known"]) == (1, 1)
    emailed = [r for r in (await session.scalars(receipts.select(Receipt))).all() if r.source == "email"]
    assert len(emailed) == 2

    await mail.save_config(session, hub, {"password": "wrong"})
    with pytest.raises(Invalid, match="app password"):
        await mail.run(session, hub)
    assert "Sign-in failed" in (await mail.load_config(session))["last_run"]["error"]


async def test_stock_entry_move_unknown_location(session, hub):
    bread = await catalog.create_product(session, hub, ProductIn(name="Bread"))
    entry = await stock.purchase(session, hub, bread.id, 1)
    with pytest.raises(Exception, match="Location 99"):
        await stock.move_entry(session, hub, entry.id, 99)
    assert (await session.get(StockEntry, entry.id)).location_id is None
