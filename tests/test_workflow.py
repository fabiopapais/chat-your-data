import unittest
from unittest.mock import Mock, patch
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from workflow import (
    get_default_llm,
    get_default_db,
    execute_query,
    handle_no_results
)


class TestWorkflow(unittest.TestCase):
    
    def setUp(self):
        self.state = {
            "tables": ["creditRisk.train"],
            "schema": "Schema test",
            "question": "Test question",
            "query": "SELECT * FROM test",
            "result": pd.DataFrame({"col": [1, 2, 3]}),
            "answer": "Test answer",
            "explanation": "Test explanation",
            "dataviz_code": "plt.plot([1,2,3])",
            "has_results": True
        }
    
    @patch.dict(os.environ, {'GOOGLE_API_KEY': 'test_key'})
    @patch('workflow.init_chat_model')
    def test_get_default_llm(self, mock_init):
        mock_llm = Mock()
        mock_init.return_value = mock_llm
        
        result = get_default_llm()
        
        mock_init.assert_called_once_with("gemini-2.5-flash-lite", model_provider="google_genai")
        self.assertEqual(result, mock_llm)
    
    @patch('workflow.get_instance')
    def test_get_default_db(self, mock_get_instance):
        mock_db = Mock()
        mock_get_instance.return_value = mock_db
        
        result = get_default_db()
        
        self.assertEqual(result, mock_db)
    
    @patch('workflow.get_default_db')
    def test_execute_query_success(self, mock_get_db):
        mock_db = Mock()
        mock_db.run_query.return_value = pd.DataFrame({"count": [10]})
        mock_get_db.return_value = mock_db
        
        result = execute_query(self.state)
        
        self.assertTrue(result["has_results"])
        self.assertIsInstance(result["result"], pd.DataFrame)
    
    @patch('workflow.get_default_db')
    def test_execute_query_empty(self, mock_get_db):
        mock_db = Mock()
        mock_db.run_query.return_value = pd.DataFrame()
        mock_get_db.return_value = mock_db
        
        result = execute_query(self.state)
        
        self.assertFalse(result["has_results"])
    
    @patch('workflow.get_default_db')
    def test_execute_query_error(self, mock_get_db):
        mock_db = Mock()
        mock_db.run_query.side_effect = Exception("DB Error")
        mock_get_db.return_value = mock_db
        
        result = execute_query(self.state)
        
        self.assertFalse(result["has_results"])
        self.assertIn("Error executing query", result["result"])
    
    def test_handle_no_results(self):
        result = handle_no_results(self.state)
        
        self.assertIn("não retornou nenhum resultado", result["answer"])


if __name__ == '__main__':
    unittest.main()
