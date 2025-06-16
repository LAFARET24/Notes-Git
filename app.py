import os
import io
import datetime
import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# --- Konfiguracja ---
DRIVE_FILE_NAME = "notes_git_data.txt"  # Nowa nazwa pliku na notatki
SCOPES = ["https://www.googleapis.com/auth/drive"]

# --- Funkcje Google Drive (z drobną modyfikacją do dopisywania) ---
@st.cache_resource
def get_drive_service():
    try:
        creds_info = {
            "type": st.secrets.gcp_service_account.type,
            "project_id": st.secrets.gcp_service_account.project_id,
            "private_key_id": st.secrets.gcp_service_account.private_key_id,
            "private_key": st.secrets.gcp_service_account.private_key.replace('\\n', '\n'),
            "client_email": st.secrets.gcp_service_account.client_email,
            "client_id": st.secrets.gcp_service_account.client_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": st.secrets.gcp_service_account.client_x509_cert_url,
            "universe_domain": "googleapis.com"
        }
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception as e:
        st.error(f"Błąd podczas łączenia z Google Drive: {e}")
        return None

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
    except HttpError:
        return ""

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

# --- Główna logika aplikacji ---
st.set_page_config(page_title="Notes Git", page_icon="📝")
st.title("📝 Notes Git")
st.caption("Twój inteligentny pamiętnik zasilany przez AI.")

# --- Inicjalizacja ---
try:
    genai.configure(api_key=st.secrets.GEMINI_API_KEY)
    drive_service = get_drive_service()
    if drive_service:
        if "file_id" not in st.session_state:
            st.session_state.file_id = get_file_id(drive_service, DRIVE_FILE_NAME)
        st.success("Połączono z Twoim prywatnym archiwum na Dysku Google.")
    else:
        st.error("Nie udało się połączyć z Dyskiem Google. Sprawdź sekrety w ustawieniach aplikacji.")
        st.stop()
except Exception as e:
    st.error(f"Błąd inicjalizacji. Sprawdź klucze API w ustawieniach aplikacji. Błąd: {e}")
    st.stop()

model = genai.GenerativeModel('gemini-1.5-flash')

# --- Interfejs Użytkownika ---
prompt = st.chat_input("Zapisz notatkę lub zadaj pytanie o swoje wpisy...")

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)

    keywords_save = ["zapisz", "zanotuj", "notatka", "pamiętaj"]
    is_saving = any(keyword in prompt.lower() for keyword in keywords_save)

    with st.chat_message("assistant"):
        with st.spinner("Przetwarzam..."):
            if is_saving:
                # Logika zapisywania notatki
                today_date = datetime.date.today().strftime("%Y-%m-%d")
                new_note_entry = f"[DATA: {today_date}]\n{prompt}\n---"
                upload_notes(drive_service, st.session_state.get("file_id"), DRIVE_FILE_NAME, new_note_entry)
                st.markdown("Notatka została zapisana w Twoim archiwum.")
            else:
                # Logika zadawania pytania
                notes_content = ""
                if st.session_state.get("file_id"):
                    notes_content = download_notes(drive_service, st.session_state.file_id)

                if not notes_content.strip():
                    st.markdown("Twoje archiwum jest jeszcze puste. Zapisz pierwszą notatkę używając słowa 'Zapisz', np. 'Zapisz: dzisiaj był dobry dzień.'")
                else:
                    system_prompt = (
                        "Jesteś asystentem, który odpowiada na pytania wyłącznie na podstawie dostarczonych notatek z pamiętnika. "
                        "Przeanalizuj poniższe notatki i odpowiedz na pytanie użytkownika. Jeśli nie znajdujesz odpowiedzi w notatkach, powiedz o tym. "
                        "Nie wymyślaj informacji.\n\n"
                        "--- MOJE NOTATKI ---\n"
                        f"{notes_content}\n"
                        "--- KONIEC NOTATEK ---\n\n"
                        f"PYTANIE UŻYTKOWNIKA: {prompt}"
                    )
                    response = model.generate_content(system_prompt)
                    st.markdown(response.text)