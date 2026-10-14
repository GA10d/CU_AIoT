import gradio as gr
import whisper


def system_init():
    whisper_model = whisper.load_model("tiny.en")
    return whisper_model

def process_input(audio, text, whisper_model):
    text = (text or "").strip()
    user_input = ""
    if text:
        user_input = text
    elif audio is not None:
        result = whisper_model.transcribe(audio, fp16=False)
        user_input = result["text"].strip()
    else:
        return "[ERROR]: invalid_input, please provide audio or text.", "", ""

    if not user_input:
        return "[ERROR]: invalid_input, please provide audio or text.", "", ""

    llm_response = f"Placeholder for LLM response: {user_input}"
    smartwatch_response = "Placeholder for smartwatch response"

    return user_input, llm_response, smartwatch_response


def set_ui(whisper_model):
    def handle_input(audio, text):
        return process_input(audio, text, whisper_model)

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
    whisper_model = system_init()
    ui = set_ui(whisper_model)
    ui.launch(debug=False, share=True)