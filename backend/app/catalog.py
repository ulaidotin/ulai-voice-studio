"""What the agent editor offers. Values are what Ulai's hosted Gemini agents accept."""

MODELS = [
    {
        "id": "gemini-live-2.5-flash-native-audio",
        "name": "Gemini 2.5 Flash · Native audio",
        "description": "Speech-to-speech with natural prosody and low latency.",
    },
]
DEFAULT_MODEL = MODELS[0]["id"]

# Gemini Live prebuilt voices and the character Google gives each.
VOICES = [
    {"id": "Puck", "style": "Upbeat"},
    {"id": "Zephyr", "style": "Bright"},
    {"id": "Charon", "style": "Informative"},
    {"id": "Kore", "style": "Firm"},
    {"id": "Fenrir", "style": "Excitable"},
    {"id": "Leda", "style": "Youthful"},
    {"id": "Orus", "style": "Firm"},
    {"id": "Aoede", "style": "Breezy"},
    {"id": "Callirrhoe", "style": "Easy-going"},
    {"id": "Autonoe", "style": "Bright"},
    {"id": "Enceladus", "style": "Breathy"},
    {"id": "Iapetus", "style": "Clear"},
    {"id": "Umbriel", "style": "Easy-going"},
    {"id": "Algieba", "style": "Smooth"},
    {"id": "Despina", "style": "Smooth"},
    {"id": "Erinome", "style": "Clear"},
    {"id": "Algenib", "style": "Gravelly"},
    {"id": "Rasalgethi", "style": "Informative"},
    {"id": "Laomedeia", "style": "Upbeat"},
    {"id": "Achernar", "style": "Soft"},
    {"id": "Alnilam", "style": "Firm"},
    {"id": "Schedar", "style": "Even"},
    {"id": "Gacrux", "style": "Mature"},
    {"id": "Pulcherrima", "style": "Forward"},
    {"id": "Achird", "style": "Friendly"},
    {"id": "Zubenelgenubi", "style": "Casual"},
    {"id": "Vindemiatrix", "style": "Gentle"},
    {"id": "Sadachbia", "style": "Lively"},
    {"id": "Sadaltager", "style": "Knowledgeable"},
    {"id": "Sulafat", "style": "Warm"},
]
DEFAULT_VOICE = "Puck"

# "" lets the model detect the caller's language.
LANGUAGES = [
    {"id": "", "name": "Auto-detect"},
    {"id": "en-US", "name": "English (US)"},
    {"id": "en-GB", "name": "English (UK)"},
    {"id": "en-IN", "name": "English (India)"},
    {"id": "en-AU", "name": "English (Australia)"},
    {"id": "hi-IN", "name": "Hindi"},
    {"id": "ta-IN", "name": "Tamil"},
    {"id": "te-IN", "name": "Telugu"},
    {"id": "kn-IN", "name": "Kannada"},
    {"id": "ml-IN", "name": "Malayalam"},
    {"id": "mr-IN", "name": "Marathi"},
    {"id": "bn-IN", "name": "Bengali"},
    {"id": "gu-IN", "name": "Gujarati"},
    {"id": "ar-XA", "name": "Arabic"},
    {"id": "es-ES", "name": "Spanish (Spain)"},
    {"id": "es-US", "name": "Spanish (US)"},
    {"id": "fr-FR", "name": "French"},
    {"id": "de-DE", "name": "German"},
    {"id": "it-IT", "name": "Italian"},
    {"id": "pt-BR", "name": "Portuguese (Brazil)"},
    {"id": "nl-NL", "name": "Dutch"},
    {"id": "ja-JP", "name": "Japanese"},
    {"id": "ko-KR", "name": "Korean"},
    {"id": "id-ID", "name": "Indonesian"},
    {"id": "th-TH", "name": "Thai"},
    {"id": "vi-VN", "name": "Vietnamese"},
    {"id": "tr-TR", "name": "Turkish"},
    {"id": "pl-PL", "name": "Polish"},
    {"id": "ru-RU", "name": "Russian"},
]

MODEL_IDS = {m["id"] for m in MODELS}
VOICE_IDS = {v["id"] for v in VOICES}
LANGUAGE_IDS = {lang["id"] for lang in LANGUAGES}
