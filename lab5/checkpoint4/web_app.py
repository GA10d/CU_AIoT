# web_app.py
import asyncio
import gradio as gr
import whisper

from agent_system import SmartwatchAssistant


def system_init():
    whisper_model = whisper.load_model("tiny.en")
    assistant = SmartwatchAssistant()
    return whisper_model, assistant


async def process_input(audio, text, whisper_model, assistant):
    text = (text or "").strip()

    if text:
        user_input = text
    elif audio is not None:
        result = await asyncio.to_thread(
            whisper_model.transcribe,
            audio,
            fp16=False,
        )
        user_input = result["text"].strip()
    else:
        return "[ERROR]: no input, please provide audio or text.", "", ""

    if not user_input:
        return "[ERROR]: user_input is empty, please provide audio or text.", "", ""

    llm_response = await assistant.get_response(user_input)
    smartwatch_response = "Placeholder for smartwatch response"

    return user_input, llm_response, smartwatch_response


def set_ui(whisper_model, assistant):
    async def handle_input(audio, text):
        return await process_input(
            audio,
            text,
            whisper_model,
            assistant,
        )

    return gr.Interface(
        fn=handle_input,
        inputs=[
            gr.Audio(
                sources=["microphone"],
                type="filepath",
                label="Voice Input",
            ),
            gr.Textbox(
                label="Text Input (optional)",
                placeholder="Type your query here...",
            ),
        ],
        outputs=[
            gr.Textbox(label="Transcription/Input"),
            gr.Textbox(label="LLM Response"),
            gr.Textbox(label="Smartwatch Response"),
        ],
        title="Voice Assistant",
        description="My capabilities: XXX",
        flagging_mode="never",
    )


if __name__ == "__main__":
    whisper_model, assistant = system_init()
    ui = set_ui(whisper_model, assistant)
    ui.launch(debug=False, share=True)