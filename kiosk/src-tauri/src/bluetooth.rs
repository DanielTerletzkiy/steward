//! Pairing Bluetooth barcode scanners through BlueZ's D-Bus API, for the kiosk page's Bluetooth panel.
//! Scanners pair with "just works"; older ones that ask for a PIN get 0000. A paired scanner is
//! trusted, so it reconnects by itself after a restart.

use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct Device {
    pub address: String,
    pub name: Option<String>,
    pub icon: Option<String>,
    pub paired: bool,
    pub trusted: bool,
    pub connected: bool,
}

#[derive(Debug, Serialize)]
pub struct Status {
    pub powered: bool,
    pub devices: Vec<Device>,
}

/// What went wrong, as a code the kiosk page translates (no_adapter, blocked, not_found,
/// pair_failed, busy, failed) and BlueZ's own message.
#[derive(Debug, Serialize)]
pub struct Failure {
    pub code: &'static str,
    pub detail: String,
}

impl Failure {
    fn new(code: &'static str, detail: impl ToString) -> Self {
        Failure { code, detail: detail.to_string() }
    }
}

pub type Result<T> = std::result::Result<T, Failure>;

#[cfg(target_os = "linux")]
mod bluez {
    use std::time::Duration;

    use bluer::agent::Agent;
    use bluer::{Adapter, Address, ErrorKind, Session};
    use futures::{pin_mut, StreamExt};
    use tokio::sync::Mutex;

    use super::{Device, Failure, Result, Status};

    /// One Bluetooth action at a time: a search and a pairing at once confuse most adapters.
    static BUSY: Mutex<()> = Mutex::const_new(());

    impl From<bluer::Error> for Failure {
        fn from(err: bluer::Error) -> Self {
            let code = match err.kind {
                ErrorKind::NotReady | ErrorKind::NotPermitted if err.message.to_lowercase().contains("rfkill") => {
                    "blocked"
                }
                ErrorKind::NotReady => "blocked",
                ErrorKind::DoesNotExist | ErrorKind::NotFound => "not_found",
                ErrorKind::AuthenticationFailed
                | ErrorKind::AuthenticationRejected
                | ErrorKind::AuthenticationCanceled
                | ErrorKind::AuthenticationTimeout
                | ErrorKind::ConnectionAttemptFailed => "pair_failed",
                ErrorKind::InProgress => "busy",
                _ => "failed",
            };
            Failure::new(code, err)
        }
    }

    async fn adapter() -> Result<(Session, Adapter)> {
        let session = Session::new().await.map_err(|err| Failure::new("no_adapter", err))?;
        let adapter = session.default_adapter().await.map_err(|err| Failure::new("no_adapter", err))?;
        Ok((session, adapter))
    }

    async fn power_on(adapter: &Adapter) -> Result<()> {
        if !adapter.is_powered().await? {
            adapter.set_powered(true).await?;
        }
        Ok(())
    }

    async fn describe(adapter: &Adapter, address: Address) -> Result<Device> {
        let device = adapter.device(address)?;
        Ok(Device {
            address: address.to_string(),
            name: device.name().await?,
            icon: device.icon().await?,
            paired: device.is_paired().await?,
            trusted: device.is_trusted().await?,
            connected: device.is_connected().await?,
        })
    }

    /// Scanners and keyboards first, then the ones with a name.
    async fn known(adapter: &Adapter) -> Result<Vec<Device>> {
        let mut devices = Vec::new();
        for address in adapter.device_addresses().await? {
            if let Ok(device) = describe(adapter, address).await {
                devices.push(device);
            }
        }
        devices.sort_by_key(|d| {
            (
                !d.icon.as_deref().unwrap_or("").starts_with("input"),
                d.name.is_none(),
                d.name.clone().unwrap_or_default(),
            )
        });
        Ok(devices)
    }

    pub async fn available() -> bool {
        adapter().await.is_ok()
    }

    pub async fn status() -> Result<Status> {
        let _busy = BUSY.lock().await;
        let (_session, adapter) = adapter().await?;
        let powered = power_on(&adapter).await.is_ok();
        let devices = known(&adapter).await?.into_iter().filter(|d| d.paired).collect();
        Ok(Status { powered, devices })
    }

    pub async fn scan(seconds: u64) -> Result<Vec<Device>> {
        let _busy = BUSY.try_lock().map_err(|_| Failure::new("busy", "Bluetooth is busy"))?;
        let (_session, adapter) = adapter().await?;
        power_on(&adapter).await?;
        {
            // Discovery runs while the stream is alive.
            let events = adapter.discover_devices().await?;
            pin_mut!(events);
            let until = tokio::time::sleep(Duration::from_secs(seconds.clamp(4, 30)));
            tokio::pin!(until);
            loop {
                tokio::select! {
                    _ = &mut until => break,
                    event = events.next() => if event.is_none() { break },
                }
            }
        }
        known(&adapter).await
    }

    fn address(text: &str) -> Result<Address> {
        text.trim()
            .to_uppercase()
            .parse()
            .map_err(|_| Failure::new("failed", format!("Not a Bluetooth address: {text}")))
    }

    pub async fn pair(text: &str) -> Result<Device> {
        let address = address(text)?;
        let _busy = BUSY.try_lock().map_err(|_| Failure::new("busy", "Bluetooth is busy"))?;
        let (session, adapter) = adapter().await?;
        power_on(&adapter).await?;
        let device = adapter.device(address)?;
        if !device.is_paired().await? {
            // An agent with no input or output: BlueZ pairs with "just works".
            let agent = session.register_agent(Agent { request_default: true, ..Default::default() }).await?;
            let mut result = attempt(&device).await;
            drop(agent);
            if matches!(&result, Err(f) if f.code == "pair_failed") {
                // An older scanner that wants a PIN: the usual one is 0000.
                let agent = session
                    .register_agent(Agent {
                        request_default: true,
                        request_pin_code: Some(Box::new(|_| Box::pin(async { Ok("0000".to_string()) }))),
                        ..Default::default()
                    })
                    .await?;
                result = attempt(&device).await;
                drop(agent);
            }
            result?;
        }
        device.set_trusted(true).await?;
        // Many scanners connect by themselves right after pairing; don't wait long for the others.
        if !device.is_connected().await.unwrap_or(false) {
            let _ = tokio::time::timeout(Duration::from_secs(15), device.connect()).await;
        }
        describe(&adapter, address).await
    }

    async fn attempt(device: &bluer::Device) -> Result<()> {
        match tokio::time::timeout(Duration::from_secs(40), device.pair()).await {
            Ok(Ok(())) => Ok(()),
            Ok(Err(err)) if err.kind == ErrorKind::AlreadyExists => Ok(()),
            Ok(Err(err)) => Err(err.into()),
            Err(_) => Err(Failure::new("pair_failed", "no answer from the device")),
        }
    }

    pub async fn remove(text: &str) -> Result<()> {
        let address = address(text)?;
        let _busy = BUSY.lock().await;
        let (_session, adapter) = adapter().await?;
        adapter.remove_device(address).await?;
        Ok(())
    }
}

#[cfg(target_os = "linux")]
pub use bluez::{available, pair, remove, scan, status};

#[cfg(not(target_os = "linux"))]
mod elsewhere {
    use super::{Device, Failure, Result, Status};

    fn none<T>() -> Result<T> {
        Err(Failure::new("no_adapter", "Bluetooth pairing needs Linux with BlueZ"))
    }
    pub async fn available() -> bool {
        false
    }
    pub async fn status() -> Result<Status> {
        none()
    }
    pub async fn scan(_: u64) -> Result<Vec<Device>> {
        none()
    }
    pub async fn pair(_: &str) -> Result<Device> {
        none()
    }
    pub async fn remove(_: &str) -> Result<()> {
        none()
    }
}

#[cfg(not(target_os = "linux"))]
pub use elsewhere::{available, pair, remove, scan, status};
