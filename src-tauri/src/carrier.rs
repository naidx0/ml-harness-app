//! A streaming wire from the page to its own engine.
//!
//! `engine_fetch` carries one request and hands back the whole body when the
//! engine closes the connection. That was enough for the old frontend, whose
//! event reader was a long-poll. OpenCode's interface reads its event stream
//! as a live response body - every tool call and message lands the moment the
//! engine writes it - so a carrier that waits for the end would hold a
//! running turn's progress back until the turn finished.
//!
//! This carrier keeps the property `engine_fetch` exists for (the page's
//! requests to 127.0.0.1 never go through the browser's networking, so no
//! CORS or private-network rule can cut the window off from its engine) and
//! adds streaming: the response head arrives as one frame, then the body as it
//! is read, then an end frame. The page wraps those in a real `Response` with
//! a `ReadableStream` body, so their client cannot tell it from `fetch`.
//!
//! HTTP/1.0 with `Connection: close`, as `engine_request` sends: the engine's
//! server then delimits the body by closing the socket rather than chunking
//! it, so there is no transfer encoding to decode here.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::{Shutdown, TcpStream};
use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;

/// One frame of a carried response, in the order they are sent.
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum Frame {
    Head {
        status: u16,
        headers: Vec<(String, String)>,
    },
    Chunk {
        data: String,
    },
    End,
    Error {
        message: String,
    },
}

/// Open streams, so the page can cancel one. Shutting the socket down is what
/// unblocks the reading thread; dropping a handle would not.
static OPEN: Mutex<Option<HashMap<u32, TcpStream>>> = Mutex::new(None);

pub fn cancel(id: u32) {
    if let Ok(mut open) = OPEN.lock() {
        if let Some(stream) = open.get_or_insert_with(HashMap::new).remove(&id) {
            let _ = stream.shutdown(Shutdown::Both);
        }
    }
}

/// Only this machine. The same rule `engine_request` enforces, for the same
/// reason: the page must not be able to use the shell as a proxy to anywhere.
pub fn split_loopback(url: &str) -> Result<(String, String), String> {
    let rest = url
        .strip_prefix("http://")
        .ok_or_else(|| format!("only http:// loopback urls are carried, got {url}"))?;
    let (authority, path) = rest.split_once('/').unwrap_or((rest, ""));
    let host = authority.split(':').next().unwrap_or("");
    if host != "127.0.0.1" && host != "localhost" {
        return Err("the shell only carries requests to this machine".into());
    }
    Ok((authority.to_string(), format!("/{path}")))
}

/// Headers the carrier writes itself, so a page-supplied copy is dropped.
fn owned_header(name: &str) -> bool {
    matches!(
        name.to_ascii_lowercase().as_str(),
        "host" | "content-length" | "connection" | "transfer-encoding"
    )
}

pub fn request_bytes(
    method: &str,
    authority: &str,
    path: &str,
    headers: &[(String, String)],
    body: &[u8],
) -> Vec<u8> {
    let mut head = format!("{method} {path} HTTP/1.0\r\nHost: {authority}\r\n");
    for (name, value) in headers {
        // A header carrying a line break would let the page write its own
        // request line. Refused, not escaped.
        if owned_header(name) || name.contains(['\r', '\n']) || value.contains(['\r', '\n']) {
            continue;
        }
        head.push_str(&format!("{name}: {value}\r\n"));
    }
    head.push_str(&format!("Content-Length: {}\r\nConnection: close\r\n\r\n", body.len()));
    let mut out = head.into_bytes();
    out.extend_from_slice(body);
    out
}

/// Parse a response head (everything before the blank line).
pub fn parse_head(raw: &[u8]) -> Option<(u16, Vec<(String, String)>)> {
    let text = std::str::from_utf8(raw).ok()?;
    let mut lines = text.split("\r\n");
    let status = lines.next()?.split_whitespace().nth(1)?.parse().ok()?;
    let headers = lines
        .filter_map(|line| {
            let (name, value) = line.split_once(':')?;
            Some((name.trim().to_string(), value.trim().to_string()))
        })
        .collect();
    Some((status, headers))
}

/// Split off the longest valid UTF-8 prefix. A read can end in the middle of a
/// multi-byte character; the tail waits for the next read rather than arriving
/// as a replacement character in the middle of a word.
pub fn take_utf8(buffer: &mut Vec<u8>) -> String {
    let valid = match std::str::from_utf8(buffer) {
        Ok(_) => buffer.len(),
        Err(error) => error.valid_up_to(),
    };
    let rest = buffer.split_off(valid);
    let text = String::from_utf8(std::mem::replace(buffer, rest)).unwrap_or_default();
    text
}

/// Carry one request, sending frames as they happen. Blocking: run it on a
/// worker thread.
pub fn carry(
    id: u32,
    url: &str,
    method: &str,
    headers: &[(String, String)],
    body: &[u8],
    mut send: impl FnMut(Frame),
) {
    let result = (|| -> Result<(), String> {
        let (authority, path) = split_loopback(url)?;
        let mut stream = TcpStream::connect(&authority).map_err(|e| e.to_string())?;
        // An event stream is quiet for as long as nothing happens. The engine
        // ends it on its own schedule; this only stops a dead socket hanging a
        // thread for ever.
        stream
            .set_read_timeout(Some(Duration::from_secs(900)))
            .map_err(|e| e.to_string())?;
        if let Ok(mut open) = OPEN.lock() {
            if let Ok(clone) = stream.try_clone() {
                open.get_or_insert_with(HashMap::new).insert(id, clone);
            }
        }
        stream
            .write_all(&request_bytes(method, &authority, &path, headers, body))
            .map_err(|e| e.to_string())?;

        let mut pending: Vec<u8> = Vec::new();
        let mut headed = false;
        let mut block = [0u8; 16384];
        loop {
            let read = match stream.read(&mut block) {
                Ok(0) => break,
                Ok(n) => n,
                // A cancelled stream reads as an error on some platforms; it
                // is an ending, not a failure.
                Err(_) if !is_open(id) => break,
                Err(error) => return Err(error.to_string()),
            };
            pending.extend_from_slice(&block[..read]);
            if !headed {
                let Some(split) = pending.windows(4).position(|w| w == b"\r\n\r\n") else {
                    continue;
                };
                let (status, headers) =
                    parse_head(&pending[..split]).ok_or("the engine sent an unreadable response head")?;
                pending.drain(..split + 4);
                send(Frame::Head { status, headers });
                headed = true;
            }
            let data = take_utf8(&mut pending);
            if !data.is_empty() {
                send(Frame::Chunk { data });
            }
        }
        if !headed {
            return Err("the engine closed the connection before answering".into());
        }
        if !pending.is_empty() {
            send(Frame::Chunk {
                data: String::from_utf8_lossy(&pending).into_owned(),
            });
        }
        Ok(())
    })();
    if let Ok(mut open) = OPEN.lock() {
        open.get_or_insert_with(HashMap::new).remove(&id);
    }
    match result {
        Ok(()) => send(Frame::End),
        Err(message) => send(Frame::Error { message }),
    }
}

fn is_open(id: u32) -> bool {
    OPEN.lock()
        .map(|mut open| open.get_or_insert_with(HashMap::new).contains_key(&id))
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn only_this_machine_is_carried() {
        assert!(split_loopback("http://127.0.0.1:8078/oc/api/info").is_ok());
        assert!(split_loopback("http://localhost:8078/").is_ok());
        assert!(split_loopback("http://example.com/").is_err());
        // A host that merely starts with the loopback digits is somewhere else.
        assert!(split_loopback("http://127.0.0.1.example.com/").is_err());
        assert!(split_loopback("https://127.0.0.1/").is_err());
    }

    #[test]
    fn the_page_cannot_write_its_own_request_line() {
        let headers = vec![
            ("X-Evil".to_string(), "a\r\nGET /other HTTP/1.0".to_string()),
            ("Content-Length".to_string(), "999".to_string()),
            ("Authorization".to_string(), "Basic abc".to_string()),
        ];
        let text = String::from_utf8(request_bytes("POST", "127.0.0.1:1", "/x", &headers, b"{}")).unwrap();
        assert!(!text.contains("/other"));
        assert!(!text.contains("999"));
        assert!(text.contains("Authorization: Basic abc\r\n"));
        assert!(text.contains("Content-Length: 2\r\n"));
    }

    #[test]
    fn a_character_split_across_reads_waits_for_its_other_half() {
        let word = "caf\u{e9}".as_bytes().to_vec();
        let mut buffer = word[..word.len() - 1].to_vec();
        assert_eq!(take_utf8(&mut buffer), "caf");
        assert_eq!(buffer.len(), 1);
        buffer.push(*word.last().unwrap());
        assert_eq!(take_utf8(&mut buffer), "\u{e9}");
        assert!(buffer.is_empty());
    }

    #[test]
    fn frames_arrive_in_order_and_the_body_streams() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            let mut scratch = [0u8; 1024];
            let _ = socket.read(&mut scratch);
            socket
                .write_all(b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\n\r\ndata: one\n\n")
                .unwrap();
            socket.flush().unwrap();
            thread::sleep(Duration::from_millis(50));
            socket.write_all(b"data: two\n\n").unwrap();
        });
        let mut frames = Vec::new();
        carry(
            1,
            &format!("http://127.0.0.1:{port}/oc/api/event"),
            "GET",
            &[],
            b"",
            |frame| frames.push(frame),
        );
        assert_eq!(
            frames.first(),
            Some(&Frame::Head {
                status: 200,
                headers: vec![("content-type".into(), "text/event-stream".into())]
            })
        );
        let body: String = frames
            .iter()
            .filter_map(|f| match f {
                Frame::Chunk { data } => Some(data.as_str()),
                _ => None,
            })
            .collect();
        assert_eq!(body, "data: one\n\ndata: two\n\n");
        // Two writes 50 ms apart were two frames, not one buffered body.
        assert!(frames.iter().filter(|f| matches!(f, Frame::Chunk { .. })).count() >= 2);
        assert_eq!(frames.last(), Some(&Frame::End));
    }

    #[test]
    fn a_refused_connection_is_an_error_frame_not_a_hang() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        let mut frames = Vec::new();
        carry(2, &format!("http://127.0.0.1:{port}/"), "GET", &[], b"", |f| frames.push(f));
        assert!(matches!(frames.as_slice(), [Frame::Error { .. }]));
    }
}
