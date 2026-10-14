import asyncio
import json
import os
from pathlib import Path

import gradio as gr
import whisper
from dotenv import load_dotenv

from agent_system import SmartwatchAssistant
from command_protocol import CommandError, validate_command
from smartwatch_client import SmartwatchClient


def system_init():
    load_dotenv(Path(__file__).resolve().parent / ".env")
    host = os.environ.get("WATCH_HOST", "").strip()
    client = None
    if host:
        client = SmartwatchClient(
            host=host,
            port=int(os.environ.get("WATCH_PORT", "8080")),
            timeout=float(os.environ.get("WATCH_TIMEOUT", "20")),
        )
    whisper_model = whisper.load_model("tiny.en")
    assistant = SmartwatchAssistant()
    return whisper_model, assistant, client


def error_response(code, message):
    return json.dumps({"ok": False, "error": {"code": code, "message": message}},
                      ensure_ascii=False, indent=2)


async def process_input(audio, text, whisper_model, assistant, client):
    text = (text or "").strip()
    if text:
        user_input = text
    elif audio is not None:
        try:
            result = await asyncio.to_thread(whisper_model.transcribe, audio, fp16=False)
            user_input = result["text"].strip()
        except Exception as error:
            return "[ERROR]: speech recognition failed: {}".format(error), "", ""
    else:
        return "[ERROR]: provide audio or text.", "", ""
    if not user_input:
        return "[ERROR]: no speech recognized.", "", ""

    try:
        llm_response = await assistant.get_response(user_input)
    except Exception as error:
        return user_input, "[ERROR]: LLM request failed: {}".format(error), ""

    try:
        command = json.loads(llm_response)
    except (ValueError, TypeError):
        return user_input, llm_response, error_response("invalid_json", "LLM returned invalid JSON")
    try:
        validate_command(command)
    except CommandError as error:
        return user_input, llm_response, error_response(error.code, str(error))
    if client is None:
        return user_input, llm_response, error_response(
            "not_configured", "Set WATCH_HOST in .env to the ESP32 IP, then restart web_app.py")

    try:
        # Socket I/O runs in a worker thread so the Gradio event loop stays free.
        response = await asyncio.to_thread(client.send_request, command)
    except OSError as error:
        return user_input, llm_response, error_response(
            "connection_failed", "ESP32 {}:{}: {}. Check device state before retrying.".format(
                client.host, client.port, error))
    except ValueError as error:
        return user_input, llm_response, error_response("invalid_response", str(error))
    return user_input, llm_response, json.dumps(response, ensure_ascii=False, indent=2)


def set_ui(whisper_model, assistant, client):
    async def handle_input(audio, text):
        return await process_input(audio, text, whisper_model, assistant, client)

    return gr.Interface(
        fn=handle_input,
        inputs=[
            gr.Audio(sources=["microphone"], type="filepath", label="Voice Input"),
            gr.Textbox(label="Text Input (optional)", placeholder="Type your query here..."),
        ],
        outputs=[
            gr.Textbox(label="Transcription/Input"),
            gr.Textbox(label="LLM Response"),
            gr.Textbox(label="Smartwatch Response"),
        ],
        title="Voice Assistant",
        description="Control the smartwatch by voice or text.",
        flagging_mode="never",
    )


if __name__ == "__main__":
    whisper_model, assistant, client = system_init()
    ui = set_ui(whisper_model, assistant, client)
    ui.launch(debug=False, share=True)
