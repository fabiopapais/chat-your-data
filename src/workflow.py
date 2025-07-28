from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END
from langchain.chat_models import init_chat_model

import os
from typing import TypedDict
from dotenv import load_dotenv

from database import get_instance
from system_prompts import (
    write_query_system_prompt,
    answer_system_prompt,
    explain_system_prompt,
    dataviz_system_prompt,
)

from langchain_community.llms import Ollama
from langchain_openai import ChatOpenAI

import chainlit as cl

load_dotenv()

def get_default_llm():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is required")
    return init_chat_model("gemini-2.5-flash", model_provider="google_genai")

def get_default_db():
    return get_instance()


class GraphState(TypedDict):
    tables: list
    schema: str
    question: str
    query: str
    result: str
    answer: str
    explanation: str
    dataviz_code: str
    has_results: bool


def write_query(state: GraphState, llm=None) -> dict:
    """Generate SQL query based on the question and schema"""

    if llm is None:
        llm = get_default_llm()

    user_prompt = "Pergunta: {question}"

    query_prompt = ChatPromptTemplate(
        [("system", write_query_system_prompt), ("user", user_prompt)]
    )

    chain = query_prompt | llm | StrOutputParser()

    try:
        query = chain.invoke(
            {
                "question": state["question"],
                "tables": "\n".join(state["tables"]),
                "schema": state["schema"],
            }
        )

        # check if llm used code blocks
        query = query.strip()
        if query.startswith("```sql"):
            query = query.replace("```sql", "").replace("```", "").strip()

        return {"query": query}

    except Exception as e:
        print(f"Error generating query: {e}")
        raise Exception({"query": f"-- Error generating query: {e}"})


def execute_query(state: GraphState, db=None) -> dict:
    """Execute the generated SQL query"""
    
    if db is None:
        db = get_default_db()

    try:
        result_df = db.run_query(state["query"])

        if (not result_df.empty) and len(result_df) > 0 and not result_df.isnull().all().all():
            return {"result": result_df, "has_results": True}
        else:
            return {"result": "Nenhum resultado encontrado.", "has_results": False}

    except Exception as e:
        error_msg = f"Error executing query: {e}"
        return {"result": error_msg, "has_results": False}


def generate_answer(state: GraphState, llm=None) -> dict:
    """Generate a natural language answer based on the query results"""
    
    if llm is None:
        llm = get_default_llm()

    chain = answer_system_prompt | llm | StrOutputParser()

    try:
        result_str = str(state["result"])
        if len(result_str) > 10000: # prevent big context sizes
            truncated_result = state["result"].head(100).to_string()
            result_for_llm = f"Resultado truncado (primeiras 100 linhas de {len(state['result'])} total):\n{truncated_result}"
        else:
            result_for_llm = state["result"]

        answer = chain.invoke(
            {
                "question": state["question"],
                "query": state["query"],
                "result": result_for_llm,
            }
        )

        return {"answer": answer.strip()}

    except Exception as e:
        return {"answer": f"Error generating answer: {e}"}


def explain_answer(state: GraphState, llm=None) -> dict:
    """Provides an explanation of how the answer was derived"""
    
    if llm is None:
        llm = get_default_llm()

    chain = explain_system_prompt | llm | StrOutputParser()

    try:
        result_str = str(state["result"])
        if len(result_str) > 10000: # prevent big context sizes
            truncated_result = state["result"].head(100).to_string()
            result_for_llm = f"Resultado truncado (primeiras 100 linhas de {len(state['result'])} total):\n{truncated_result}"
        else:
            result_for_llm = state["result"]

        explanation = chain.invoke(
            {
                "question": state["question"],
                "query": state["query"],
                "result": result_for_llm,  # Use processed result instead of raw DataFrame
                "answer": state["answer"],
            }
        )

        return {"explanation": explanation.strip()}

    except Exception as e:
        return {"explanation": f"Error generating explanation: {e}"}


def create_visualization(state: GraphState, llm=None) -> dict:
    """Generates matplotlib code to visualize the results"""
    
    if llm is None:
        llm = get_default_llm()

    chain = dataviz_system_prompt | llm | StrOutputParser()

    try:
        if not state["result"].empty:
            columns = [f"'{col}', " for col in state["result"].columns]
            sample_data = state["result"].head(5).to_string()
            result_for_viz = f"Amostra dos dados (5 primeiras linhas):\n{sample_data}"
        else:
            columns = "No columns available"
            result_for_viz = str(state["result"])

        visualization_code = chain.invoke(
            {
                "question": state["question"],
                "query": state["query"],
                "result": result_for_viz,
                "columns": columns,
            }
        )

        # check if llm used code blocks
        visualization_code = visualization_code.strip()
        if visualization_code.startswith("```python"):
            visualization_code = (
                visualization_code.replace("```python", "").replace("```", "").strip()
            )

        return {"dataviz_code": visualization_code.strip()}

    except Exception as e:
        return {"dataviz_code": f"# Error: {e}"}


def handle_no_results(state: GraphState) -> dict:
    return {"answer": f"A consulta SQL não retornou nenhum resultado."}


def should_continue_workflow(state: GraphState) -> str:
    if state.get("has_results", False):
        return "generate_answer"
    else:
        return "handle_no_results"


def create_sql_workflow():
    """Create and return a LangGraph workflow"""

    workflow = StateGraph(GraphState)

    # nodes
    workflow.add_node("write_query", write_query)
    workflow.add_node("execute_query", execute_query)
    workflow.add_node("generate_answer", generate_answer)
    workflow.add_node("explain_answer", explain_answer)
    workflow.add_node("create_visualization", create_visualization)
    workflow.add_node("handle_no_results", handle_no_results)

    # flow
    workflow.set_entry_point("write_query")
    workflow.add_edge("write_query", "execute_query")

    # route based if query returned results
    workflow.add_conditional_edges(
        "execute_query",
        should_continue_workflow,
        {
            "generate_answer": "generate_answer",
            "handle_no_results": "handle_no_results",
        },
    )

    # if results exist
    workflow.add_edge("generate_answer", "explain_answer")
    workflow.add_edge("explain_answer", "create_visualization")
    workflow.add_edge("create_visualization", END)

    # if no results
    workflow.add_edge("handle_no_results", END)

    return workflow.compile()


if __name__ == "__main__":
    app = create_sql_workflow()
    db = get_default_db()

    initial_state = {
        "tables": db.get_tables(),
        "schema": db.get_schemas(),
        "question": "Quais os 10 estados com mais mulheres?",
        "query": "",
        "result": "",
        "answer": "",
        "explanation": "",
        "dataviz_code": "",
        "has_results": False,
    }

    current_state = initial_state.copy()

    print("Starting SQL Analysis Workflow...")
    print("=" * 50)

    try:
        for step_output in app.stream(initial_state):
            print(step_output)
            print("-" * 70)
            current_state.update(step_output)

    except Exception as e:
        print(f"Workflow error: {e}")

    print(current_state)

# TODO: suporte à outros modelos
# TODO: retry para queries que falharem
# TODO: checar se a pergunta é válida