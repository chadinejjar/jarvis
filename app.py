import os
import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from google import genai

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="JARVIS Desk", page_icon="🤖", layout="wide")

# ---------- STYLING ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
.stApp {
    background: radial-gradient(ellipse at 50% 15%, #10264a 0%, transparent 45%),
                linear-gradient(145deg, #050b17, #091426 55%, #050b17);
    color: #eaf2ff;
    font-family: Inter, sans-serif;
}
header[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1500px; padding: 3.5rem 2rem 2rem; }
h1, h2, h3, p, label { color: #eaf2ff; }
.panel-label {
    color: #69cfff; font-weight: 700; font-size: .9rem;
    letter-spacing: 1.5px; margin-bottom: .8rem;
}
.small-muted { color: #8fa6c5; font-size: .85rem; }
.jarvis-title {
    font-size: clamp(2.2rem, 4vw, 3.7rem); font-weight: 800;
    letter-spacing: -2px; text-align: center; margin: .5rem 0 0;
    background: linear-gradient(90deg, #fff, #70d8ff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.jarvis-subtitle {
    color: #8faed5; text-align: center; letter-spacing: 4px;
    font-size: .75rem; margin: .5rem 0 1rem;
}
div[data-testid="stChatInput"] {
    border: 1px solid #258dff; border-radius: 18px; background: #08172b;
}
div.stButton > button {
    border-radius: 12px; border: 1px solid #20558a;
    background: #102746; color: #eaf5ff; min-height: 42px;
}
div.stButton > button:hover {
    border-color: #36cfff; color: white; box-shadow: 0 0 18px #168bff30;
}
div[data-testid="stChatMessage"] {
    background: #0b1b30; border: 1px solid #1a3859;
    border-radius: 14px; padding: .8rem;
}
hr { border-color: #193452; }
</style>
<div style="position:fixed;top:14px;left:22px;z-index:999999;color:#91aabd;
font-size:11px;font-weight:600;letter-spacing:2px;">
JARVIS DESK <span style="color:#00d9ff;">v1.0</span>
</div>
""", unsafe_allow_html=True)

# ---------- API KEY ----------
key_file = Path.home() / ".config/jarvis-desk/.env"
api_key = os.environ.get("GEMINI_API_KEY", "")
if not api_key and key_file.exists():
    for line in key_file.read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

# ---------- SESSION STATE ----------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "detect_location" not in st.session_state:
    st.session_state.detect_location = False
if "voice_language" not in st.session_state:
    st.session_state.voice_language = "en-US"
if "speak_replies" not in st.session_state:
    st.session_state.speak_replies = True
if "voice_transcript" not in st.session_state:
    st.session_state.voice_transcript = ""
if "last_processed_voice" not in st.session_state:
    st.session_state.last_processed_voice = ""

# ---------- CLOCK + HEADER ----------
top_left, top_right = st.columns([4, 1])
with top_left:
    st.markdown('<div class="small-muted">JARVIS DESK · PERSONAL AI</div>', unsafe_allow_html=True)
with top_right:
    st.markdown('<div style="text-align:right;color:#42e6a4;">● SYSTEM ONLINE</div>', unsafe_allow_html=True)

st.markdown(
    '<div class="jarvis-title">JARVIS Desk</div>'
    '<div class="jarvis-subtitle">LISTEN · THINK · RESPOND</div>',
    unsafe_allow_html=True,
)

left, center, right = st.columns([1, 1.6, 1], gap="large")

# ---------- LEFT PANEL ----------
with left:
    st.markdown('<div class="panel-label">LOCAL TIME</div>', unsafe_allow_html=True)
    components.html("""
    <div style="font-family:Inter,Arial,sans-serif;color:#eaf6ff;padding:8px 0 18px;">
      <div id="clock" style="font-size:38px;font-weight:300;letter-spacing:2px;font-variant-numeric:tabular-nums;">00:00:00</div>
      <div id="date" style="margin-top:7px;font-size:11px;letter-spacing:1.5px;color:#8ba9bd;text-transform:uppercase;"></div>
    </div>
    <script>
    function tick() {
      const now = new Date();
      document.getElementById('clock').textContent = now.toLocaleTimeString('nl-NL', {
        hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
      });
      document.getElementById('date').textContent = now.toLocaleDateString('nl-NL', {
        weekday:'long', day:'numeric', month:'long', year:'numeric'
      });
    }
    tick(); setInterval(tick, 1000);
    </script>
    """, height=100)

    st.divider()
    st.markdown('<div class="panel-label">📍 LOCAL WEATHER</div>', unsafe_allow_html=True)
    if st.button("Detect location", use_container_width=True):
        st.session_state.detect_location = True

    if st.session_state.detect_location:
        try:
            loc_response = requests.get("https://ipwho.is/", timeout=10)
            loc_response.raise_for_status()
            loc = loc_response.json()
            if not loc.get("success", False):
                raise RuntimeError("IP location lookup failed")
            city = loc.get("city") or "Unknown city"
            country = loc.get("country") or ""
            lat, lon = loc.get("latitude"), loc.get("longitude")
            tz_data = loc.get("timezone") or {}
            tz = tz_data.get("id") if isinstance(tz_data, dict) else tz_data
            if lat is None or lon is None or not tz:
                raise RuntimeError("Location or timezone unavailable")

            weather_response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,relative_humidity_2m",
                    "timezone": "auto",
                },
                timeout=10,
            )
            weather_response.raise_for_status()
            weather = weather_response.json()["current"]
            # Ensure the returned timezone is valid, though the browser clock above uses device time.
            ZoneInfo(tz)
            st.markdown(f"### {city}")
            st.caption(country)
            st.metric("🌡️ Temperature", f"{weather['temperature_2m']} °C")
            st.caption(f"Feels like {weather['apparent_temperature']} °C · Humidity {weather['relative_humidity_2m']}%")
        except Exception as error:
            st.warning(f"Weather unavailable: {error}")
    else:
        st.caption("Detect your approximate location to show current weather.")

# ---------- CENTER: CUSTOM MICROPHONE ----------
with center:
    st.markdown(
        '<div class="jarvis-title" style="font-size:1.5rem;letter-spacing:0;">Speak to JARVIS</div>'
        '<div class="mic-help" style="text-align:center;color:#a9c4e7;margin:.5rem 0 1rem;">'
        'Click the glowing microphone to start or stop recording.</div>',
        unsafe_allow_html=True,
    )

    # The custom browser component owns the visible button and uses the Web Speech API.
    # It sends the recognized transcript to Streamlit using a query parameter.
    # Browser speech recognition is supported mainly in Chrome/Chromium.
    components.html(
        f"""
        <div style="display:flex;flex-direction:column;align-items:center;gap:12px;font-family:Inter,Arial,sans-serif;">
          <button id="mic" aria-label="Start or stop speaking" style="
            width:190px;height:190px;border-radius:50%;cursor:pointer;
            display:flex;align-items:center;justify-content:center;font-size:78px;color:white;
            background:radial-gradient(circle at 35% 25%,#59d9ff,#1265ec 52%,#071d55);
            border:3px solid #a3eaff;box-shadow:0 0 22px #159dff,0 0 65px #087aff70,inset 0 0 24px #ffffff45;
            transition:all .2s ease;">🎙️</button>
          <div id="status" style="font-size:12px;color:#9bb6d2;text-align:center;">READY · CLICK TO SPEAK</div>
          <div id="heard" style="max-width:100%;color:#d8eaff;font-size:13px;text-align:center;overflow-wrap:anywhere;"></div>
        </div>
        <script>
        (() => {{
          const button = document.getElementById('mic');
          const status = document.getElementById('status');
          const heard = document.getElementById('heard');
          const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
          let recognition = null;
          let listening = false;
          let finalTranscript = '';

          if (!SpeechRecognition) {{
            status.textContent = 'Speech recognition is not supported in this browser.';
            button.disabled = true;
            button.style.opacity = '.45';
            return;
          }}

          recognition = new SpeechRecognition();
          recognition.continuous = false;
          recognition.interimResults = true;
          recognition.lang = {json.dumps(st.session_state.voice_language)};

          button.addEventListener('click', () => {{
            if (listening) {{
              recognition.stop();
              return;
            }}
            finalTranscript = '';
            heard.textContent = '';
            try {{
              recognition.start();
              listening = true;
              button.style.background = 'radial-gradient(circle at 35% 25%,#ff8b8b,#e52c68 52%,#591538)';
              button.style.boxShadow = '0 0 28px #ff477e,0 0 70px #ff477e70,inset 0 0 24px #ffffff45';
              status.textContent = 'LISTENING · CLICK TO FINISH';
            }} catch (e) {{
              status.textContent = 'Could not start microphone. Allow microphone access and try again.';
            }}
          }});

          recognition.onresult = (event) => {{
            let interim = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {{
              const transcript = event.results[i][0].transcript;
              if (event.results[i].isFinal) finalTranscript += transcript;
              else interim += transcript;
            }}
            heard.textContent = finalTranscript || interim;
          }};

          recognition.onerror = (event) => {{
            status.textContent = 'Microphone error: ' + event.error;
            listening = false;
            resetButton();
          }};

          recognition.onend = () => {{
            listening = false;
            resetButton();
            const transcript = finalTranscript.trim() || heard.textContent.trim();
            if (transcript) {{
              status.textContent = 'SENT TO JARVIS';
              const url = new URL(window.parent.location.href);
              url.searchParams.set('voice_text', transcript);
              url.searchParams.set('voice_nonce', String(Date.now()));
              window.parent.location.href = url.toString();
            }} else if (status.textContent.startsWith('LISTENING')) {{
              status.textContent = 'READY · CLICK TO SPEAK';
            }}
          }};

          function resetButton() {{
            button.style.background = 'radial-gradient(circle at 35% 25%,#59d9ff,#1265ec 52%,#071d55)';
            button.style.boxShadow = '0 0 22px #159dff,0 0 65px #087aff70,inset 0 0 24px #ffffff45';
          }}
        }})();
        </script>
        """,
        height=270,
        scrolling=False,
    )

    st.selectbox(
        "Voice recognition language",
        options=["en-US", "nl-NL", "en-GB"],
        format_func=lambda x: {"en-US": "English (US)", "nl-NL": "Nederlands", "en-GB": "English (UK)"}[x],
        key="voice_language",
    )
    st.session_state.speak_replies = st.toggle("🔊 Speak JARVIS replies", value=st.session_state.speak_replies)
    typed_prompt = st.chat_input("Message JARVIS...")

# ---------- RIGHT: CONVERSATION ----------
with right:
    st.markdown('<div class="panel-label">💬 CONVERSATION</div>', unsafe_allow_html=True)
    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    if not st.session_state.messages:
        st.info("Hi! I'm JARVIS. Click the glowing microphone or type a message.")
    for message in st.session_state.messages[-8:]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# ---------- PROCESS INPUT ----------
voice_text = st.query_params.get("voice_text", "")
voice_nonce = st.query_params.get("voice_nonce", "")
if isinstance(voice_text, list):
    voice_text = voice_text[0] if voice_text else ""
if isinstance(voice_nonce, list):
    voice_nonce = voice_nonce[0] if voice_nonce else ""

prompt = typed_prompt
if voice_text and voice_nonce and voice_nonce != st.session_state.last_processed_voice:
    st.session_state.last_processed_voice = voice_nonce
    st.query_params.clear()
    if not prompt:
        prompt = voice_text
        st.toast(f"You said: {voice_text}")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    if not api_key:
        answer = "API key missing. Check ~/.config/jarvis-desk/.env"
    else:
        try:
            client = genai.Client(api_key=api_key)
            history = []
            for message in st.session_state.messages[-12:]:
                history.append({
                    "role": "user" if message["role"] == "user" else "model",
                    "parts": [{"text": message["content"]}],
                })
            with st.spinner("JARVIS is thinking..."):
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=history,
                    config={
                        "system_instruction": (
                            "You are JARVIS, a helpful personal AI assistant. "
                            "Answer in the language the user uses. Be clear, friendly, and practical. "
                            "Never claim to perform computer actions unless a tool actually did them."
                        )
                    },
                )
            answer = response.text or "I couldn't generate a response."
        except Exception as error:
            answer = (
                "I couldn't reach the AI service. Check your API key, internet connection, "
                "model availability, and usage limits.\n\n"
                f"Details: {error}"
            )

    st.session_state.messages.append({"role": "assistant", "content": answer})

    if st.session_state.speak_replies:
        components.html(
            f"""
            <script>
            const text = {json.dumps(answer)};
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = "en-US";
            window.speechSynthesis.speak(utterance);
            </script>
            """,
            height=0,
        )
    st.rerun()
