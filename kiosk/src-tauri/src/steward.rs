//! Talking to Steward before its page is open: is it there, and trading a pairing code for the key.

use std::time::Duration;

/// Steward's address from what someone typed or pasted: the kiosk address, a pairing link or just
/// host and port. Everything from /#/ or /auth/ on is dropped, and http:// is assumed.
pub fn origin(url: &str) -> String {
    let url = url.trim();
    let url = url.split("/#").next().unwrap_or(url);
    let url = url.split("/auth/").next().unwrap_or(url);
    let url = url.trim_end_matches('/');
    if url.is_empty() || url.contains("://") {
        url.to_string()
    } else {
        format!("http://{url}")
    }
}

fn agent() -> ureq::Agent {
    ureq::AgentBuilder::new().timeout_connect(Duration::from_secs(4)).timeout(Duration::from_secs(10)).build()
}

/// Ok when Steward's page answers; otherwise why not, for the waiting screen.
pub fn reachable(origin: &str) -> Result<(), String> {
    match agent().get(&format!("{origin}/")).call() {
        Ok(_) => Ok(()),
        Err(ureq::Error::Status(code, _)) => Err(format!("HTTP {code}")),
        Err(ureq::Error::Transport(err)) => Err(err.to_string()),
    }
}

/// The terminal's key for a pairing code from Steward → Settings → Kitchen terminals.
pub fn redeem(origin: &str, code: &str) -> Result<String, String> {
    let answer = agent()
        .post(&format!("{origin}/auth/terminal/redeem"))
        .send_json(serde_json::json!({ "code": code }))
        .map_err(|err| match err {
            ureq::Error::Status(400 | 401 | 404 | 422, _) => "code".to_string(),
            ureq::Error::Status(code, _) => format!("HTTP {code}"),
            ureq::Error::Transport(err) => err.to_string(),
        })?;
    let body: serde_json::Value = answer.into_json().map_err(|err| err.to_string())?;
    body["key"].as_str().map(str::to_string).ok_or_else(|| "no key in Steward's answer".to_string())
}

#[cfg(test)]
mod tests {
    use super::origin;

    #[test]
    fn origin_from_what_people_paste() {
        assert_eq!(origin("http://pi.local:8095/#/kiosk"), "http://pi.local:8095");
        assert_eq!(origin("http://pi.local:8095/auth/terminal?code=AB"), "http://pi.local:8095");
        assert_eq!(origin(" homeassistant.local:8095/ "), "http://homeassistant.local:8095");
        assert_eq!(origin("https://steward.example.org"), "https://steward.example.org");
    }
}
