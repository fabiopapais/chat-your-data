from typing import Dict, Any
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import chainlit as cl
from workflow import (
    write_query, 
    execute_query, 
    generate_answer, 
    explain_answer, 
    create_visualization,
    handle_no_results,
    get_default_llm,
    get_default_db,
    GraphState
)

def create_plot_figures(code: str, result_df: pd.DataFrame) -> list:
    """Execute visualization code and return a list of matplotlib figures."""
    try:
        figs = []
        exec_globals = {
            'plt': plt,
            'pd': pd,
            'sns': sns,
            'np': np,
            'df': result_df,
            'figs': figs,
        }
        
        initial_figures_count = len(plt.get_fignums())

        exec(code, exec_globals)
        current_figures = [plt.figure(fignum) for fignum in plt.get_fignums() if fignum >= initial_figures_count]
        
        all_figs = list(set(figs + current_figures))
        
        for fig in current_figures:
            plt.close(fig)

        return all_figs
        
    except Exception as e:
        print(f"Error creating visualization: {e}")
        return []


class WorkflowOrchestrator:
    """Orchestrates workflow manually and callbacks to chainlit"""
    
    def __init__(self, llm=None, db=None):
        self.llm = llm or get_default_llm()
        self.db = db or get_default_db()
        self.state = GraphState()
                
    def initialize_state(self, question: str) -> Dict[str, Any]:
        """Initialize the workflow state"""
        self.state = GraphState(
            tables=self.db.get_tables(),
            schema=self.db.get_schemas(),
            question=question,
            query="",
            result="",
            answer="",
            explanation="",
            dataviz_code="",
            has_results=False,
        )
        return self.state.copy()
    
    
    def step_write_query(self) -> Dict[str, Any]:
        result = write_query(self.state, self.llm)
        self.state.update(result)
        return result['query']
    
    def step_execute_query(self) -> Dict[str, Any]:
        result = execute_query(self.state, self.db)
        self.state.update(result)
        return result['result']
    
    def step_generate_answer(self) -> Dict[str, Any]:
        result = generate_answer(self.state, self.llm)
        self.state.update(result)
        return result['answer']
    
    def step_explain_answer(self) -> Dict[str, Any]:
        
        result = explain_answer(self.state, self.llm)
        self.state.update(result)
        return result['explanation']
    
    def step_create_visualization(self) -> Dict[str, Any]:
        
        result = create_visualization(self.state, self.llm)
        self.state.update(result)
        return result['dataviz_code']
    
    def step_handle_no_results(self) -> Dict[str, Any]:
        
        result = handle_no_results(self.state)
        self.state.update(result)
        return result['answer']


    async def run_chainlit_workflow(self, question: str):
        """Run the complete workflow and send chainlit messages"""
        self.initialize_state(question)
        
        # step 1: query generation
        async with cl.Step(name="geração da query SQL") as step:
            step.output = "Gerando consulta SQL..." 
            await step.update()

            query_result = self.step_write_query()

            step.output = f"Query SQL gerada:\n```sql\n{query_result}\n```"
            await step.update()
        
        # step 2: execute query
        async with cl.Step(name="execução da query SQL") as step:
            step.output = "Executando consulta SQL..."
            await step.update()

            execute_result = self.step_execute_query()
            if self.state.get("has_results", False):
                step.output = f"Query executada com sucesso, {len(execute_result)} registro(s) encontrados."
            else:
                step.output = "Query executada, mas não retornou resultados."
            await step.update()

        if self.state.get("has_results", False):
            
            # send results
            result_df = self.state.get("result")
            if not result_df.empty:
                display_df = result_df.head(100)
                elements = [cl.Dataframe(data=display_df, display="inline")]
                message_content = f"## Resultados da query{' (mostrando as primeiras 100 linhas):' if len(result_df) > 100 else ':'}"
                await cl.Message(content=message_content, elements=elements).send()

            # step 3 : interpret results
            async with cl.Step(name="interpretação dos resultados") as step:
                step.output = "Interpretando resultados..."
                await step.update()
                answer_result = self.step_generate_answer()                
                await step.remove()

            await cl.Message(content=answer_result).send()

            # step 4: explain query
            async with cl.Step(name="explicação da query") as step:
                step.output = "Explicando a consulta SQL..."
                await step.update()
                explanation_result = self.step_explain_answer()

                step.output = explanation_result
                await step.update()
            
            # step 5: create visualization
            async with cl.Step(name="criação da visualização") as step:
                step.output = "Gerando código de visualização dos dados..."
                await step.update()

                dataviz_code = self.step_create_visualization()
                step.output = f"```python\n{dataviz_code}\n```"
                await step.update()

            if isinstance(result_df, pd.DataFrame) and dataviz_code.strip():
                try:
                    figs = create_plot_figures(dataviz_code, result_df)
                    
                    if figs:
                        elements = []
                        for i, fig in enumerate(figs):
                            elements.append(cl.Pyplot(
                                name=f"visualization_{i}",
                                figure=fig,
                                display="inline",
                            ))
                        await cl.Message(
                            content="## Visualização dos Dados",
                            elements=elements
                        ).send()
                    else:
                        await cl.Message(
                            content="Erro na Visualização\nNenhuma figura foi gerada pelo código de visualização."
                        ).send()
                except Exception as viz_error:
                    await cl.Message(
                        content=f"Erro na Visualização\n{viz_error}"
                    ).send()
            else:
                await cl.Message(content="Não foi possível gerar visualização: Código vazio.").send()
        else:            
            no_results_result = self.step_handle_no_results()
            await cl.Message(content=no_results_result).send()

def create_orchestrator(llm=None, db=None) -> WorkflowOrchestrator:
    """Create a new workflow orchestrator instance"""
    return WorkflowOrchestrator(llm, db)