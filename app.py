import os
import io
import datetime
import json
import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from streamlit_mic_recorder import mic_recorder
from gtts import gTTS

# --- Konfiguracja ---
DRIVE_FILE_NAME = "notes_git_data.txt"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# --- INTELIGENTNA FUNKCJA LOGOWANIA (działa lokalnie i w chmurze) ---
@st.cache_resource
def get_drive_service():
    # Metoda dla wdrożonej aplikacji w Streamlit Cloud (używa Secrets)
    if hasattr(st, 'secrets') and "gcp_service_account" in st.secrets:
        try:
            creds_info = dict(st.secrets.gcp_service_account)
            # Poniższa linijka jest kluczowa dla poprawnego formatowania klucza w chmurze
            creds_info['private_key'] = creds_info['private_key'].replace('\\n', '\n')
            creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            service = build("drive", "v3", credentials=creds)
            return service
        except Exception as e:
            st.error(f"Błąd logowania przez Service Account: {e}")
            return None
    # Metoda dla lokalnego komputera (używa plików .json)
    else:
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())
        try:
            service = build("drive", "v3", credentials=creds)
            return service
        except Exception as e:
            st.error(f"Błąd logowania lokalnego: {e}")
            return None

# --- Funkcja do zamiany tekstu na mowę ---
def text_to_audio(text):
    try:
        tts = gTTS(text=text, lang='pl')
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        return audio_fp
    except Exception as e:
        print(f"Błąd gTTS: {e}")
        return None
        
# Reszta funkcji do obsługi plików
def get_file_id(service, file_name):
    query = f"name='{file_name}' and trashed=false"
    response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = response.get('files', [])
    return files[0].get('id') if files else None

def download_notes(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue().decode('utf-8')
    except HttpError: return ""

def upload_notes(service, file_id, file_name, new_note_content):
    existing_content = ""
    if file_id:
        existing_content = download_notes(service, file_id)
    full_content = existing_content.strip() + f"\n\n{new_note_content}"
    media = MediaIoBaseUpload(io.BytesIO(full_content.encode('utf-8')), mimetype='text/plain', resumable=True)
    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        file_metadata = {'name': file_name}
        response = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        st.session_state.file_id = response.get('id')

# --- Główna logika aplikacji Streamlit ---
st.set_page_config(page_title="Notes Git", page_icon="📝")
st.title("📝 Notes Git")
st.caption("Twój inteligentny pamiętnik zasilany przez AI.")

# Inteligentne ładowanie klucza Gemini
try:
    api_key = st.secrets.get("GEMINI_API_KEY") if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets else os.environ.get('GEMINI_API_KEY')
    if not api_key:
        st.error("Błąd: Nie znaleziono klucza GEMINI_API_KEY. Ustaw go w Secrets (dla wersji online) lub jako zmienną środowiskową (dla wersji lokalnej).")
        st.stop()
    genai.configure(api_key=api_key)
except Exception as e:
    st.error(f"Błąd konfiguracji Gemini API: {e}")
    st.stop()

# Inicjalizacja usług
drive_service = get_drive_service()
if not drive_service:
    st.stop()

if "file_id" not in st.session_state:
    with st.spinner("Sprawdzanie archiwum na Dysku Google..."):
        st.session_state.file_id = get_file_id(drive_service, DRIVE_FILE_NAME)

st.success("Połączono z Twoim prywatnym archiwum na Dysku Google.")
model = genai.GenerativeModel('gemini-1.5-flash')

# Funkcja do obsługi prompta
def handle_prompt(prompt_text):
    with st.chat_message("user"):
        st.markdown(prompt_text)

    keywords_save = ["zapisz", "zanotuj", "notatka", "pamiętaj"]
    is_saving = any(keyword in prompt_text.lower() for keyword in keywords_save)

    with st.chat_message("assistant"):
        with st.spinner("Przetwarzam..."):
            if is_saving:
                today_date = datetime.date.today().strftime("%Y-%m-%d")
                new_note_entry = f"[DATA: {today_date}]\n{prompt_text}\n---"
                upload_notes(drive_service, st.session_state.get("file_id"), DRIVE_FILE_NAME, new_note_entry)
                response_text = "Notatka została zapisana w Twoim archiwum."
            else:
                notes_content = ""
                if st.session_state.get("file_id"):
                    notes_content = download_notes(drive_service, st.session_state.file_id)
                if not notes_content.strip():
                    response_text = "Twoje archiwum jest jeszcze puste. Zapisz pierwszą notatkę!"
                else:
                    system_prompt = (
                        "Jesteś asystentem, który odpowiada na pytania wyłącznie na podstawie dostarczonych notatek z pamiętnika. "
                        f"Oto notatki:\n{notes_content}\n\nPYTANIE: {prompt_text}"
                    )
                    response = model.generate_content(system_prompt)
                    response_text = response.text
            
            st.markdown(response_text)
            sound_file = text_to_audio(response_text)
            if sound_file:
                st.audio(sound_file, autoplay=True)

# Sekcja nagrywania głosu
st.write("Naciśnij i mów, aby dodać notatkę głosową lub zadać pytanie:")
audio_data = mic_recorder(start_prompt="▶️ Mów", stop_prompt="⏹️ Stop", just_once=True, key='mic1')

if audio_data and audio_data['bytes']:
    audio_bytes = audio_data['bytes']
    with st.spinner("Rozpoznaję mowę..."):
        audio_file = {"mime_type": "audio/wav", "data": audio_bytes}
        prompt_from_voice = genai.GenerativeModel('gemini-1.5-flash').generate_content(["Zamień tę mowę na tekst: ", audio_file]).text
        handle_prompt(prompt_from_voice)

# Pole do wpisywania tekstu
if prompt_from_text := st.chat_input("...lub napisz tutaj"):
    handle_prompt(prompt_from_text)