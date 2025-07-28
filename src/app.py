import chainlit as cl
from dotenv import load_dotenv
from orchestrator import create_orchestrator

load_dotenv()

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Qual a média de idade por UF?",
            message="Qual a média de idade por UF?",
            icon="/public/icons/map.png"
            ),

        cl.Starter(
            label="Quantos registros existem por classe social?",
            message="Quantos registros existem por classe social?",
            icon="/public/icons/class.png"
            ),
        cl.Starter(
            label="Qual a distribuição de inadimplência por sexo?",
            message="Qual a distribuição de inadimplência por sexo?",
            icon="/public/icons/sex.png"
            )
        ]

@cl.on_chat_start
async def on_chat_start():
    """Init chat session and workflow"""
    
    orchestrator = create_orchestrator()
    cl.user_session.set("orchestrator", orchestrator)

@cl.on_message
async def main(message: cl.Message):
    """Handle messages with orchestrator workflow"""
    
    orchestrator = cl.user_session.get("orchestrator")

    try:
        await orchestrator.run_chainlit_workflow(message.content)
    except Exception as e:
        await cl.Message(content=f"Desculpe, ocorreu um erro no fluxo: {e}").send()