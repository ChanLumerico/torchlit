use crossterm::{
    event::{self, DisableMouseCapture, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Alignment, Constraint, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Cell, Gauge, Paragraph, Row, Table, Wrap},
    Frame, Terminal,
};
use serde::Deserialize;
use serde_json::Value;
use std::{
    collections::VecDeque,
    fs::OpenOptions,
    io::{self, BufRead, Write},
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};

// ─── Protocol ─────────────────────────────────────────────────────────────────

#[derive(Deserialize, Debug, Clone)]
#[serde(tag = "type", rename_all = "lowercase")]
enum Message {
    Init {
        exp_name: String,
        model_name: Option<String>,
        total_params: Option<String>,
        trainable_params: Option<String>,
        device: Option<String>,
        total_steps: Option<u64>,
    },
    Step {
        step: u64,
        metrics: Value,
        elapsed: f64,
    },
    Done {
        step: u64,
    },
}

// ─── App State ─────────────────────────────────────────────────────────────────

#[derive(Default, Clone)]
struct MetricHistory {
    name: String,
    values: VecDeque<f64>,
}

#[derive(Default, Clone)]
struct AppState {
    exp_name: String,
    model_name: String,
    total_params: String,
    device: String,
    total_steps: Option<u64>,

    current_step: u64,
    elapsed: f64,
    steps_per_sec: f64,
    is_done: bool,

    latest_metrics: Vec<(String, f64)>,
    histories: Vec<MetricHistory>,
}

impl AppState {
    fn eta_str(&self) -> String {
        if let Some(total) = self.total_steps {
            if self.steps_per_sec > 0.0 && self.current_step < total {
                let remaining = (total - self.current_step) as f64 / self.steps_per_sec;
                return format_duration(remaining);
            }
        }
        "—".to_string()
    }

    fn progress_ratio(&self) -> f64 {
        match self.total_steps {
            Some(t) if t > 0 => (self.current_step as f64 / t as f64).min(1.0),
            _ => 0.0,
        }
    }
}

fn format_duration(secs: f64) -> String {
    let s = secs as u64;
    let h = s / 3600;
    let m = (s % 3600) / 60;
    let s = s % 60;
    if h > 0 {
        format!("{:02}:{:02}:{:02}", h, m, s)
    } else {
        format!("{:02}:{:02}", m, s)
    }
}

// ─── Rendering ────────────────────────────────────────────────────────────────

fn draw(frame: &mut Frame, state: &AppState) {
    let area = frame.area();
    let outer = Layout::vertical([
        Constraint::Length(3),
        Constraint::Min(0),
        Constraint::Length(3),
    ])
    .split(area);

    draw_header(frame, outer[0], state);
    draw_body(frame, outer[1], state);
    draw_footer(frame, outer[2], state);
}

fn accent_color(device: &str) -> Color {
    let d = device.to_lowercase();
    if d.contains("mps") || d.contains("apple") {
        Color::Magenta
    } else if d.contains("cuda") || d.contains("nvidia") {
        Color::Green
    } else {
        Color::Yellow
    }
}

fn draw_header(frame: &mut Frame, area: Rect, state: &AppState) {
    let dev_color = accent_color(&state.device);
    let title = Line::from(vec![
        Span::raw("  "),
        Span::styled("torchlit", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
        Span::raw("  ●  "),
        Span::styled(&state.exp_name, Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)),
        Span::raw("    │    "),
        Span::styled("Model: ", Style::default().fg(Color::DarkGray)),
        Span::styled(&state.model_name, Style::default().fg(Color::White)),
        Span::raw("  │  "),
        Span::styled("Params: ", Style::default().fg(Color::DarkGray)),
        Span::styled(&state.total_params, Style::default().fg(Color::White)),
        Span::raw("  │  "),
        Span::styled("Device: ", Style::default().fg(Color::DarkGray)),
        Span::styled(&state.device, Style::default().fg(dev_color)),
        Span::raw("  "),
    ]);
    let header = Paragraph::new(title)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Cyan))
                .title(Span::styled(
                    " ⚡ Training ",
                    Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
                )),
        )
        .alignment(Alignment::Left);
    frame.render_widget(header, area);
}

fn draw_body(frame: &mut Frame, area: Rect, state: &AppState) {
    let cols = Layout::horizontal([Constraint::Percentage(55), Constraint::Percentage(45)]).split(area);
    draw_metrics_table(frame, cols[0], state);
    draw_right_panel(frame, cols[1], state);
}

fn draw_metrics_table(frame: &mut Frame, area: Rect, state: &AppState) {
    let header_row = Row::new(vec![
        Cell::from("Metric").style(Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
        Cell::from("Value").style(Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
        Cell::from("Trend").style(Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
    ])
    .height(1)
    .style(Style::default().bg(Color::Rgb(30, 30, 50)));

    let rows: Vec<Row> = state.latest_metrics.iter().map(|(name, val)| {
        let trend = state.histories.iter().find(|h| h.name == *name).and_then(|h| {
            if h.values.len() >= 2 {
                let last = *h.values.back().unwrap();
                let prev = h.values[h.values.len() - 2];
                if last < prev { Some(("▼", Color::Green)) }
                else if last > prev { Some(("▲", Color::Red)) }
                else { Some(("─", Color::DarkGray)) }
            } else {
                None
            }
        });
        let val_str = format!("{:.4}", val);
        let (trend_sym, trend_color) = trend.unwrap_or(("  ", Color::DarkGray));
        Row::new(vec![
            Cell::from(name.as_str()).style(Style::default().fg(Color::Cyan)),
            Cell::from(val_str).style(Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            Cell::from(trend_sym).style(Style::default().fg(trend_color).add_modifier(Modifier::BOLD)),
        ])
    }).collect();

    let widths = [Constraint::Percentage(50), Constraint::Percentage(35), Constraint::Percentage(15)];
    let table = Table::new(rows, widths)
        .header(header_row)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Blue))
                .title(Span::styled(
                    " 📊 Metrics ",
                    Style::default().fg(Color::Blue).add_modifier(Modifier::BOLD),
                )),
        )
        .column_spacing(2);
    frame.render_widget(table, area);
}

fn draw_right_panel(frame: &mut Frame, area: Rect, state: &AppState) {
    let rows = Layout::vertical([
        Constraint::Length(5),
        Constraint::Length(5),
        Constraint::Min(0),
    ])
    .split(area);
    draw_progress(frame, rows[0], state);
    draw_timing(frame, rows[1], state);
    draw_sparklines(frame, rows[2], state);
}

fn draw_progress(frame: &mut Frame, area: Rect, state: &AppState) {
    let ratio = state.progress_ratio();
    let pct = (ratio * 100.0) as u16;
    let label = match state.total_steps {
        Some(t) => format!("Step {}/{} — {}%", state.current_step, t, pct),
        None => format!("Step {}", state.current_step),
    };
    let gauge = Gauge::default()
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Green))
                .title(Span::styled(
                    " 🔄 Progress ",
                    Style::default().fg(Color::Green).add_modifier(Modifier::BOLD),
                )),
        )
        .gauge_style(Style::default().fg(Color::Green).bg(Color::Rgb(20, 35, 20)))
        .ratio(ratio)
        .label(label);
    frame.render_widget(gauge, area);
}

fn draw_timing(frame: &mut Frame, area: Rect, state: &AppState) {
    let elapsed_str = format_duration(state.elapsed);
    let eta = state.eta_str();
    let sps = format!("{:.2} steps/s", state.steps_per_sec);
    let text = vec![
        Line::from(vec![
            Span::styled("Elapsed: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&elapsed_str, Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            Span::raw("   "),
            Span::styled("ETA: ", Style::default().fg(Color::DarkGray)),
            Span::styled(eta, Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::styled("Speed:   ", Style::default().fg(Color::DarkGray)),
            Span::styled(sps, Style::default().fg(Color::Cyan)),
        ]),
    ];
    let para = Paragraph::new(text)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Magenta))
                .title(Span::styled(
                    " ⏱ Timing ",
                    Style::default().fg(Color::Magenta).add_modifier(Modifier::BOLD),
                )),
        )
        .wrap(Wrap { trim: false });
    frame.render_widget(para, area);
}

fn draw_sparklines(frame: &mut Frame, area: Rect, state: &AppState) {
    if state.histories.is_empty() || area.height < 3 {
        return;
    }
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::DarkGray))
        .title(Span::styled(
            " 📈 History ",
            Style::default().fg(Color::DarkGray).add_modifier(Modifier::BOLD),
        ));
    let inner = block.inner(area);
    frame.render_widget(block, area);

    let n = state.histories.len().min(inner.height as usize);
    let spark_rows = Layout::vertical((0..n).map(|_| Constraint::Length(1)).collect::<Vec<_>>()).split(inner);
    let bars = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];

    for (i, hist) in state.histories.iter().take(n).enumerate() {
        let vals = &hist.values;
        if vals.is_empty() { continue; }
        let min = vals.iter().cloned().fold(f64::INFINITY, f64::min);
        let max = vals.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let range = (max - min).max(1e-9);
        let name_len = (hist.name.len() + 2).min(spark_rows[i].width as usize);
        let spark_width = spark_rows[i].width as usize - name_len;
        let spark_chars: String = vals.iter().rev().take(spark_width).collect::<Vec<_>>()
            .into_iter().rev()
            .map(|v| bars[(((v - min) / range) * 7.0).round() as usize].min(bars[7]))
            .collect();
        let line = Line::from(vec![
            Span::styled(format!("{:<width$}", hist.name, width = name_len), Style::default().fg(Color::DarkGray)),
            Span::styled(spark_chars, Style::default().fg(Color::Blue)),
        ]);
        frame.render_widget(Paragraph::new(line), spark_rows[i]);
    }
}

fn draw_footer(frame: &mut Frame, area: Rect, state: &AppState) {
    let status = if state.is_done {
        Span::styled(
            format!(" ✅ Training Complete — {} steps ", state.current_step),
            Style::default().fg(Color::Green).add_modifier(Modifier::BOLD),
        )
    } else {
        Span::styled(
            " Press 'q' to detach from display (training continues) ",
            Style::default().fg(Color::DarkGray),
        )
    };
    let footer = Paragraph::new(Line::from(vec![status]))
        .block(Block::default().borders(Borders::ALL).border_style(Style::default().fg(Color::DarkGray)))
        .alignment(Alignment::Center);
    frame.render_widget(footer, area);
}

// ─── Main ──────────────────────────────────────────────────────────────────────

fn main() -> io::Result<()> {
    let state = Arc::new(Mutex::new(AppState::default()));
    let state_writer = Arc::clone(&state);

    // ── Stdin reader thread (reads from REAL stdin = NDJSON pipe) ─────────────
    thread::spawn(move || {
        let stdin = io::stdin();
        let mut prev_elapsed = 0.0f64;
        let mut prev_step = 0u64;

        for line in stdin.lock().lines() {
            let Ok(line) = line else { break };
            let line = line.trim().to_string();
            if line.is_empty() { continue; }

            match serde_json::from_str::<Message>(&line) {
                Ok(Message::Init { exp_name, model_name, total_params, trainable_params, device, total_steps }) => {
                    let mut s = state_writer.lock().unwrap();
                    s.exp_name = exp_name;
                    s.model_name = model_name.unwrap_or_else(|| "—".to_string());
                    s.total_params = total_params.unwrap_or_else(|| "—".to_string());
                    s.device = device.unwrap_or_else(|| "CPU".to_string());
                    s.total_steps = total_steps;
                }
                Ok(Message::Step { step, metrics, elapsed }) => {
                    let dt = elapsed - prev_elapsed;
                    let ds = step.saturating_sub(prev_step) as f64;
                    let sps = if dt > 0.0 { ds / dt } else { 0.0 };
                    prev_elapsed = elapsed;
                    prev_step = step;

                    let mut s = state_writer.lock().unwrap();
                    s.current_step = step;
                    s.elapsed = elapsed;
                    if sps > 0.0 { s.steps_per_sec = sps; }

                    if let Value::Object(map) = &metrics {
                        let new_metrics: Vec<(String, f64)> = map.iter()
                            .filter_map(|(k, v)| v.as_f64().map(|f| (k.clone(), f)))
                            .collect();
                        let mut sorted = new_metrics.clone();
                        sorted.sort_by(|a, b| a.0.cmp(&b.0));
                        s.latest_metrics = sorted;

                        for (key, val) in new_metrics {
                            if let Some(h) = s.histories.iter_mut().find(|h| h.name == key) {
                                h.values.push_back(val);
                                if h.values.len() > 80 { h.values.pop_front(); }
                            } else {
                                let mut h = MetricHistory { name: key.clone(), values: VecDeque::new() };
                                h.values.push_back(val);
                                s.histories.push(h);
                            }
                        }
                    }
                }
                Ok(Message::Done { step }) => {
                    let mut s = state_writer.lock().unwrap();
                    s.current_step = step;
                    s.is_done = true;
                }
                Err(_) => {}
            }
        }
        // EOF on stdin — mark done
        state_writer.lock().unwrap().is_done = true;
    });

    // ── Open /dev/tty directly for the terminal so stdin can stay as the pipe ─
    let tty = OpenOptions::new().read(true).write(true).open("/dev/tty")?;
    enable_raw_mode()?;

    let mut tty_write: Box<dyn Write> = Box::new(tty);
    execute!(tty_write, EnterAlternateScreen)?;

    let backend = CrosstermBackend::new(tty_write);
    let mut terminal = Terminal::new(backend)?;

    // ── Render loop ────────────────────────────────────────────────────────────
    loop {
        {
            let s = state.lock().unwrap();
            terminal.draw(|f| draw(f, &s))?;
        }

        // Poll for keypresses — ignore errors (e.g. when running as subprocess)
        if let Ok(true) = event::poll(Duration::from_millis(100)) {
            if let Ok(Event::Key(key)) = event::read() {
                if matches!(key.code, KeyCode::Char('q') | KeyCode::Esc) {
                    break;
                }
            }
        }

        {
            let s = state.lock().unwrap();
            if s.is_done {
                // Draw the final state one more time then hold for 2s
                drop(s);
                let s = state.lock().unwrap();
                terminal.draw(|f| draw(f, &s))?;
                thread::sleep(Duration::from_secs(2));
                break;
            }
        }
    }

    // ── Cleanup ────────────────────────────────────────────────────────────────
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, DisableMouseCapture)?;
    terminal.show_cursor()?;

    Ok(())
}
