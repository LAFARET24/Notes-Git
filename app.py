import streamlit as st
import json

st.set_page_config(page_title="Diagnostyka Sekretów", layout="wide")
st.title("🕵️‍♂️ Narzędzie Diagnostyczne Sekretów")
st.write("Poniżej znajduje się to, co aplikacja odczytuje z Twoich ustawień 'Secrets' w Streamlit Cloud.")
st.info("Zrób zrzut ekranu tego okna i prześlij mi go. To pomoże nam ostatecznie zdiagnozować problem.")

if hasattr(st, 'secrets'):
    # Sprawdź, czy sekrety nie są puste
    if not st.secrets.items():
        st.error("Błąd: Wygląda na to, że sekrety są puste. Upewnij się, że zostały zapisane w panelu Streamlit.")
    else:
        st.write("---")
        st.header("Odczytane Sekrety (w formacie JSON):")
        st.write("To jest surowa reprezentacja danych. Szukamy błędów w formatowaniu lub brakujących pól.")

        # Próba konwersji sekretów na słownik i wyświetlenie jako JSON
        try:
            secrets_dict = st.secrets.to_dict()
            st.json(secrets_dict)
        except Exception as e:
            st.error(f"Nie udało się przekonwertować sekretów na format JSON do wyświetlenia. Błąd: {e}")
            st.write("Surowa zawartość sekretów:")
            st.write(st.secrets)

        st.write("---")
else:
    st.error("Krytyczny błąd: Nie znaleziono obiektu `st.secrets` w środowisku Streamlit.")