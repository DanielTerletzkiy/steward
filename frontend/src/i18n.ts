// All user-facing text. English is the source; other languages must have the same shape.

const en = {
  app: { title: 'Steward', offline: 'No live connection – reconnecting …', retry: 'Retry', error: 'Error', loadError: 'Could not load data', language: 'Language', live: 'Live', offlineShort: 'Offline' },
  nav: { today: 'Today', stock: 'Stock', shopping: 'Shopping', shoppingLong: 'Shopping list', chores: 'Chores', receipts: 'Receipts', journal: 'History' },
  common: {
    save: 'Save', cancel: 'Cancel', create: 'Create', add: 'Add', delete: 'Delete', edit: 'Edit',
    undo: 'Undo', done: 'Done', skip: 'Skip', search: 'Search', all: 'All', none: 'None', close: 'Close',
    name: 'Name', amount: 'Amount', unit: 'Unit', location: 'Location', category: 'Category', brand: 'Brand', price: 'Price',
    dueDate: 'Due on', notes: 'Notes', optional: 'optional', required: 'Required', back: 'Back', more: 'More',
    noLocation: 'No location', undone: 'Undone',
  },
  status: {
    ok: 'OK', due_soon: 'Expiring soon', expired: 'Expired', out: 'Out', below_min: 'Below minimum', opened: 'opened',
    overdue: 'Overdue', due_today: 'Due today', chore_due_soon: 'Due soon', scheduled: 'Scheduled', manual: 'Manual',
  },
  rel: {
    today: 'today', tomorrow: 'tomorrow', yesterday: 'yesterday',
    inDays: (n: number) => `in ${n} days`,
    daysAgo: (n: number) => `${n} days ago`,
    overdueDays: (n: number) => (n === 1 ? 'overdue by 1 day' : `overdue by ${n} days`),
    expiredDays: (n: number) => (n === 1 ? 'expired yesterday' : `expired ${n} days ago`),
    expiresToday: 'expires today',
    expiresIn: (n: number) => (n === 1 ? 'expires tomorrow' : `expires in ${n} days`),
    noDue: 'no best-before date',
  },
  today: {
    greetingMorning: 'Good morning', greetingDay: 'Hello', greetingEvening: 'Good evening',
    expiring: 'Expiring / expired', belowMin: 'Below minimum stock', chores: 'Chores due', tasks: 'Open tasks',
    spending: 'Spending this month', lastTrip: 'Last shopping trip', deposit: 'Deposit balance', stockValue: 'Stock value',
    productsInStock: (n: number) => `${n} products in stock`,
    trips: (n: number) => (n === 1 ? '1 trip' : `${n} trips`),
    items: (n: number) => (n === 1 ? '1 item' : `${n} items`),
    nothingExpiring: 'Nothing is expiring. All fresh!',
    nothingBelowMin: 'Everything is sufficiently stocked.',
    noChores: 'Nothing to do today. Enjoy!',
    noTasks: 'No tasks due.',
    openTasks: (n: number) => `${n} open in total`,
    depositHint: 'Negative = more bottles returned than paid for', depositSub: 'Bottles & cans',
    addToList: 'Add to shopping list',
    noReceipts: 'No receipts yet',
  },
  stock: {
    title: 'Stock', searchPlaceholder: 'Search products …', allLocations: 'All locations', allStatus: 'All',
    filterInStock: 'In stock', filterExpiring: 'Expiring', filterBelowMin: 'Below minimum', filterOut: 'Out',
    group: 'Group by location', newProduct: 'New product',
    purchase: 'Purchase', consume: 'Consume', spoil: 'Spoiled', open: 'Open',
    purchased: (name: string, amount: string) => `Added ${amount} ${name}`,
    consumed: (name: string, amount: string) => `Consumed ${amount} ${name}`,
    spoiled: (name: string) => `${name} thrown away as spoiled`,
    openedMsg: (name: string) => `${name} opened`,
    empty: 'No products found', emptyHint: 'Create a product or import a receipt.',
    value: 'Value', minStock: 'Minimum stock', dueDays: 'Shelf life (days)', dueType: 'Date type',
    bestBefore: 'Best before', expiration: 'Use by', purchaseTitle: (n: string) => `Purchase ${n}`,
    unitPrice: 'Unit price (€)', editProduct: 'Edit product', deleteProduct: 'Delete product',
    confirmDelete: (n: string) => `Really delete "${n}"? Its stock and history will be lost.`,
    entries: 'Batches', noEntries: 'Not in stock', purchasedAt: 'Bought', productSaved: 'Product saved', productDeleted: 'Product deleted',
    aliases: 'Receipt texts (aliases)', aliasesHint: 'Comma-separated, e.g. "SALAMI HAUCHFEIN"',
    count: (n: number) => (n === 1 ? '1 product' : `${n} products`),
  },
  shopping: {
    title: 'Shopping list', addPlaceholder: 'What do you need?', addMissing: 'Add missing', clearDone: 'Remove done',
    added: (n: number) => (n === 0 ? 'Nothing is missing' : n === 1 ? 'Added 1 product' : `Added ${n} products`),
    removed: (n: number) => (n === 1 ? 'Removed 1 item' : `Removed ${n} items`),
    empty: 'The list is empty', emptyHint: 'Add something above or take over missing products.',
    doneSection: (n: number) => `Done (${n})`, open: (n: number) => `${n} open`,
    deleted: 'Item deleted', allDone: 'Everything is in the basket!',
  },
  chores: {
    title: 'Chores', tasksTitle: 'Tasks', newChore: 'New chore', assignee: 'Next', everyone: 'Everyone',
    lastDone: 'Last', never: 'never', doneMsg: (n: string) => `"${n}" done`, skippedMsg: (n: string) => `"${n}" skipped`,
    empty: 'No chores', emptyHint: 'Create recurring chores such as "Clean the bathroom".',
    schedule: 'Schedule', interval: 'Interval', weekdays: 'Weekdays', assignment: 'Assignment', assignees: 'People',
    assigneesHint: 'Empty = everyone in the household', firstDue: 'First due', icon: 'Icon (mdi:…)', description: 'Description',
    schedules: { manual: 'Manual', daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly', dynamic: 'After completion' },
    assignments: { none: 'Nobody', fixed: 'Fixed person', least_done: 'Whoever did it least', rotation: 'Rotation' },
    intervalSuffix: { daily: 'day(s)', weekly: 'week(s)', monthly: 'month(s)', dynamic: 'days after completion', manual: '' },
    describe: {
      manual: 'Manual',
      daily: (n: number) => (n === 1 ? 'Daily' : `Every ${n} days`),
      weekly: (n: number) => (n === 1 ? 'Weekly' : `Every ${n} weeks`),
      monthly: (n: number) => (n === 1 ? 'Monthly' : `Every ${n} months`),
      dynamic: (n: number) => (n === 1 ? '1 day after completion' : `${n} days after completion`),
    },
    weekdayShort: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    deleteChore: 'Delete chore', confirmDelete: (n: string) => `Really delete "${n}"?`, created: 'Chore created',
    noPeople: 'No people known from Home Assistant',
  },
  tasks: {
    addPlaceholder: 'New task …', empty: 'No open tasks', emptyHint: 'All done!', showDone: 'Show done',
    doneMsg: (n: string) => `"${n}" done`, reopened: 'Reopened', deleted: 'Task deleted', due: 'due',
    defaultCategory: 'General', details: 'Details',
  },
  receipts: {
    title: 'Receipts', upload: 'Upload eBon', uploading: 'Reading …', uploaded: 'Receipt imported',
    empty: 'No receipts yet', emptyHint: 'Upload a REWE eBon (PDF) to record purchases automatically.',
    matched: (n: number) => `${n} matched`, unmatched: (n: number) => `${n} open`, stocked: 'In stock', notStocked: 'Not stocked',
    lines: 'Lines', total: 'Receipt total', lineSum: 'Sum of lines', diff: 'Difference',
    toStock: 'Put into stock', stockedMsg: (n: number) => (n === 1 ? 'Stocked 1 line' : `Stocked ${n} lines`),
    kinds: { item: 'Item', deposit: 'Deposit', deposit_return: 'Bottle return', bag: 'Bag' } as Record<string, string>,
    methods: { alias: 'Alias', fuzzy: 'Similar', manual: 'Manual' } as Record<string, string>,
    unmatchedLine: 'Not matched', choose: 'Match', change: 'Change', confirm: 'Confirm',
    pickProduct: 'Choose product', pickTitle: 'Match line', existing: 'Existing product', createNew: 'New product',
    lineMatched: 'Match saved', payment: 'Payment', confidence: 'Confidence',
    unmatchedHint: (n: number) => (n === 1 ? '1 line is not matched yet and will not be stocked.' : `${n} lines are not matched yet and will not be stocked.`),
  },
  journal: {
    title: 'History', empty: 'No entries yet',
    types: { purchase: 'Purchase', consume: 'Consumed', spoil: 'Spoiled', open: 'Opened' } as Record<string, string>,
    undone: 'undone', sources: { ui: 'App', receipt: 'Receipt', seed: 'Demo', ha: 'Home Assistant', chore: 'Chore' } as Record<string, string>,
  },
}

export type Messages = typeof en

const de: Messages = {
  app: { title: 'Steward', offline: 'Keine Live-Verbindung – verbinde neu …', retry: 'Erneut versuchen', error: 'Fehler', loadError: 'Daten konnten nicht geladen werden', language: 'Sprache', live: 'Live', offlineShort: 'Offline' },
  nav: { today: 'Heute', stock: 'Vorrat', shopping: 'Einkauf', shoppingLong: 'Einkaufsliste', chores: 'Aufgaben', receipts: 'Belege', journal: 'Verlauf' },
  common: {
    save: 'Speichern', cancel: 'Abbrechen', create: 'Anlegen', add: 'Hinzufügen', delete: 'Löschen', edit: 'Bearbeiten',
    undo: 'Rückgängig', done: 'Erledigt', skip: 'Überspringen', search: 'Suchen', all: 'Alle', none: 'Keine', close: 'Schließen',
    name: 'Name', amount: 'Menge', unit: 'Einheit', location: 'Ort', category: 'Kategorie', brand: 'Marke', price: 'Preis',
    dueDate: 'Fällig am', notes: 'Notizen', optional: 'optional', required: 'Pflichtfeld', back: 'Zurück', more: 'Mehr',
    noLocation: 'Ohne Ort', undone: 'Rückgängig gemacht',
  },
  status: {
    ok: 'OK', due_soon: 'Läuft bald ab', expired: 'Abgelaufen', out: 'Leer', below_min: 'Unter Minimum', opened: 'geöffnet',
    overdue: 'Überfällig', due_today: 'Heute fällig', chore_due_soon: 'Bald fällig', scheduled: 'Geplant', manual: 'Manuell',
  },
  rel: {
    today: 'heute', tomorrow: 'morgen', yesterday: 'gestern',
    inDays: (n: number) => `in ${n} Tagen`,
    daysAgo: (n: number) => `vor ${n} Tagen`,
    overdueDays: (n: number) => (n === 1 ? 'seit 1 Tag überfällig' : `seit ${n} Tagen überfällig`),
    expiredDays: (n: number) => (n === 1 ? 'seit gestern abgelaufen' : `seit ${n} Tagen abgelaufen`),
    expiresToday: 'läuft heute ab',
    expiresIn: (n: number) => (n === 1 ? 'läuft morgen ab' : `läuft in ${n} Tagen ab`),
    noDue: 'kein MHD',
  },
  today: {
    greetingMorning: 'Guten Morgen', greetingDay: 'Hallo', greetingEvening: 'Guten Abend',
    expiring: 'Läuft ab / abgelaufen', belowMin: 'Unter Mindestbestand', chores: 'Hausarbeiten fällig', tasks: 'Offene Aufgaben',
    spending: 'Ausgaben diesen Monat', lastTrip: 'Letzter Einkauf', deposit: 'Pfand-Saldo', stockValue: 'Vorratswert',
    productsInStock: (n: number) => `${n} Produkte im Vorrat`,
    trips: (n: number) => (n === 1 ? '1 Einkauf' : `${n} Einkäufe`),
    items: (n: number) => (n === 1 ? '1 Artikel' : `${n} Artikel`),
    nothingExpiring: 'Nichts läuft ab. Alles frisch!',
    nothingBelowMin: 'Alles ausreichend vorrätig.',
    noChores: 'Heute nichts zu tun. Genieß den Tag!',
    noTasks: 'Keine fälligen Aufgaben.',
    openTasks: (n: number) => `${n} offen insgesamt`,
    depositHint: 'Negativ = Pfand noch zurückzugeben', depositSub: 'Flaschen & Dosen',
    addToList: 'Auf die Einkaufsliste',
    noReceipts: 'Noch keine Belege',
  },
  stock: {
    title: 'Vorrat', searchPlaceholder: 'Produkt suchen …', allLocations: 'Alle Orte', allStatus: 'Alle',
    filterInStock: 'Vorrätig', filterExpiring: 'Läuft ab', filterBelowMin: 'Unter Minimum', filterOut: 'Leer',
    group: 'Nach Ort gruppieren', newProduct: 'Neues Produkt',
    purchase: 'Einkauf', consume: 'Verbrauchen', spoil: 'Verdorben', open: 'Öffnen',
    purchased: (name: string, amount: string) => `${amount} ${name} hinzugefügt`,
    consumed: (name: string, amount: string) => `${amount} ${name} verbraucht`,
    spoiled: (name: string) => `${name} als verdorben entsorgt`,
    openedMsg: (name: string) => `${name} geöffnet`,
    empty: 'Keine Produkte gefunden', emptyHint: 'Lege ein Produkt an oder importiere einen Beleg.',
    value: 'Wert', minStock: 'Mindestbestand', dueDays: 'Haltbarkeit (Tage)', dueType: 'Datumsart',
    bestBefore: 'Mindestens haltbar bis', expiration: 'Verbrauchen bis', purchaseTitle: (n: string) => `${n} einkaufen`,
    unitPrice: 'Stückpreis (€)', editProduct: 'Produkt bearbeiten', deleteProduct: 'Produkt löschen',
    confirmDelete: (n: string) => `„${n}“ wirklich löschen? Bestand und Verlauf gehen verloren.`,
    entries: 'Chargen', noEntries: 'Nicht im Vorrat', purchasedAt: 'Gekauft', productSaved: 'Produkt gespeichert', productDeleted: 'Produkt gelöscht',
    aliases: 'Bon-Texte (Aliasse)', aliasesHint: 'Komma-getrennt, z. B. „SALAMI HAUCHFEIN“',
    count: (n: number) => (n === 1 ? '1 Produkt' : `${n} Produkte`),
  },
  shopping: {
    title: 'Einkaufsliste', addPlaceholder: 'Was wird gebraucht?', addMissing: 'Fehlende hinzufügen', clearDone: 'Erledigte entfernen',
    added: (n: number) => (n === 0 ? 'Nichts fehlt' : n === 1 ? '1 Produkt hinzugefügt' : `${n} Produkte hinzugefügt`),
    removed: (n: number) => (n === 1 ? '1 Eintrag entfernt' : `${n} Einträge entfernt`),
    empty: 'Die Liste ist leer', emptyHint: 'Füge oben etwas hinzu oder übernimm fehlende Produkte.',
    doneSection: (n: number) => `Erledigt (${n})`, open: (n: number) => (n === 1 ? '1 offen' : `${n} offen`),
    deleted: 'Eintrag gelöscht', allDone: 'Alles im Korb!',
  },
  chores: {
    title: 'Hausarbeiten', tasksTitle: 'Aufgaben', newChore: 'Neue Hausarbeit', assignee: 'Nächste/r', everyone: 'Alle',
    lastDone: 'Zuletzt', never: 'noch nie', doneMsg: (n: string) => `„${n}“ erledigt`, skippedMsg: (n: string) => `„${n}“ übersprungen`,
    empty: 'Keine Hausarbeiten', emptyHint: 'Lege wiederkehrende Aufgaben wie „Bad putzen“ an.',
    schedule: 'Rhythmus', interval: 'Intervall', weekdays: 'Wochentage', assignment: 'Zuweisung', assignees: 'Personen',
    assigneesHint: 'Leer = alle im Haushalt', firstDue: 'Erstmals fällig', icon: 'Icon (mdi:…)', description: 'Beschreibung',
    schedules: { manual: 'Manuell', daily: 'Täglich', weekly: 'Wöchentlich', monthly: 'Monatlich', dynamic: 'Nach Erledigung' },
    assignments: { none: 'Niemand', fixed: 'Feste Person', least_done: 'Wer am wenigsten gemacht hat', rotation: 'Reihum' },
    intervalSuffix: { daily: 'Tag(e)', weekly: 'Woche(n)', monthly: 'Monat(e)', dynamic: 'Tage nach Erledigung', manual: '' },
    describe: {
      manual: 'Manuell',
      daily: (n: number) => (n === 1 ? 'Täglich' : `Alle ${n} Tage`),
      weekly: (n: number) => (n === 1 ? 'Wöchentlich' : `Alle ${n} Wochen`),
      monthly: (n: number) => (n === 1 ? 'Monatlich' : `Alle ${n} Monate`),
      dynamic: (n: number) => (n === 1 ? '1 Tag nach Erledigung' : `${n} Tage nach Erledigung`),
    },
    weekdayShort: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
    deleteChore: 'Hausarbeit löschen', confirmDelete: (n: string) => `„${n}“ wirklich löschen?`, created: 'Hausarbeit angelegt',
    noPeople: 'Keine Personen aus Home Assistant bekannt',
  },
  tasks: {
    addPlaceholder: 'Neue Aufgabe …', empty: 'Keine offenen Aufgaben', emptyHint: 'Alles erledigt!', showDone: 'Erledigte zeigen',
    doneMsg: (n: string) => `„${n}“ erledigt`, reopened: 'Wieder geöffnet', deleted: 'Aufgabe gelöscht', due: 'fällig',
    defaultCategory: 'Allgemein', details: 'Details',
  },
  receipts: {
    title: 'Belege', upload: 'eBon hochladen', uploading: 'Wird gelesen …', uploaded: 'Beleg importiert',
    empty: 'Noch keine Belege', emptyHint: 'Lade einen REWE-eBon (PDF) hoch, um Einkäufe automatisch zu erfassen.',
    matched: (n: number) => `${n} zugeordnet`, unmatched: (n: number) => `${n} offen`, stocked: 'Im Vorrat', notStocked: 'Nicht eingelagert',
    lines: 'Positionen', total: 'Summe Beleg', lineSum: 'Summe Positionen', diff: 'Differenz',
    toStock: 'In den Vorrat', stockedMsg: (n: number) => (n === 1 ? '1 Position eingelagert' : `${n} Positionen eingelagert`),
    kinds: { item: 'Artikel', deposit: 'Pfand', deposit_return: 'Pfandrückgabe', bag: 'Tüte' } as Record<string, string>,
    methods: { alias: 'Alias', fuzzy: 'Ähnlich', manual: 'Manuell' } as Record<string, string>,
    unmatchedLine: 'Nicht zugeordnet', choose: 'Zuordnen', change: 'Ändern', confirm: 'Bestätigen',
    pickProduct: 'Produkt wählen', pickTitle: 'Position zuordnen', existing: 'Vorhandenes Produkt', createNew: 'Neues Produkt',
    lineMatched: 'Zuordnung gespeichert', payment: 'Zahlung', confidence: 'Sicherheit',
    unmatchedHint: (n: number) => (n === 1 ? '1 Position ist noch nicht zugeordnet und wird nicht eingelagert.' : `${n} Positionen sind noch nicht zugeordnet und werden nicht eingelagert.`),
  },
  journal: {
    title: 'Verlauf', empty: 'Noch keine Buchungen',
    types: { purchase: 'Einkauf', consume: 'Verbraucht', spoil: 'Verdorben', open: 'Geöffnet' } as Record<string, string>,
    undone: 'rückgängig', sources: { ui: 'App', receipt: 'Beleg', seed: 'Demo', ha: 'Home Assistant', chore: 'Hausarbeit' } as Record<string, string>,
  },
}

export const LANGUAGES = { en: 'English', de: 'Deutsch' } as const
export type Language = keyof typeof LANGUAGES
const STORAGE_KEY = 'steward.lang'

function pickLanguage(): Language {
  // Explicit choice wins: ?lang=de in the URL, then the saved setting. English otherwise.
  const fromUrl = new URLSearchParams(window.location.search).get('lang')
  let saved: string | null = null
  try {
    saved = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can be blocked (private mode, sandboxed iframe); fall back to the default.
  }
  const wanted = fromUrl ?? saved
  return wanted && wanted in LANGUAGES ? (wanted as Language) : 'en'
}

export const LANG: Language = pickLanguage()
/** BCP 47 locale for dates, numbers and sorting. en-GB keeps day-month order and the 24-hour clock. */
export const LOCALE = LANG === 'de' ? 'de-DE' : 'en-GB'
export const t: Messages = LANG === 'de' ? de : en

export function setLanguage(lang: Language): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // Not persisted; the reload below still switches for this visit via the URL.
  }
  const url = new URL(window.location.href)
  url.searchParams.delete('lang')
  if (lang !== 'en') url.searchParams.set('lang', lang)
  window.location.replace(url.toString())
}
