import httpx
import pytest

from metagpt.tools.libs.supabase_manager import SupabaseManager, config


class TestSupabaseManager:
    TEST_ACCESS_TOKEN = "test_access_token"
    TEST_BASE_URL = "https://api.supabase.com/v1"
    TEST_PROJECT_REF = "test_project_ref"
    TEST_SESSION_ID = "test_session_123"

    @pytest.fixture
    def mock_httpx_client(self, mocker):
        return mocker.patch("httpx.Client")

    @pytest.fixture
    def supabase_manager(self):
        return SupabaseManager(access_token=self.TEST_ACCESS_TOKEN, management_base_url=self.TEST_BASE_URL)

    def test_initialization_with_default_values(self):
        # Setup
        manager = SupabaseManager()

        # Assert
        assert manager.access_token == config.supabase.access_token
        assert manager.management_base_url == config.supabase.management_base_url
        assert manager._default_headers == {
            "Authorization": f"Bearer {config.supabase.access_token}",
            "Content-Type": "application/json",
        }

    def test_initialization_with_custom_values(self):
        # Setup
        manager = SupabaseManager(access_token=self.TEST_ACCESS_TOKEN, management_base_url=self.TEST_BASE_URL)

        # Assert
        assert manager.access_token == self.TEST_ACCESS_TOKEN
        assert manager.management_base_url == self.TEST_BASE_URL
        assert manager._default_headers == {
            "Authorization": f"Bearer {self.TEST_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

    def test_get_config(self, supabase_manager: SupabaseManager):
        # Exec
        config_data = supabase_manager.get_config()

        # Assert
        assert isinstance(config_data, dict)
        assert "access_token" in config_data
        assert "management_base_url" in config_data
        assert "project_ref" in config_data

    def test_execute_sql_success(self, supabase_manager: SupabaseManager, mock_httpx_client, mocker):
        # Mock
        mock_response = mocker.MagicMock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status.return_value = None
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mock_httpx_client.return_value.__enter__.return_value = mock_client

        # Setup
        test_sql = "SELECT * FROM test_table;"

        # Exec
        result = supabase_manager.execute_sql(test_sql, self.TEST_PROJECT_REF)

        # Assert
        assert result == {"result": "success"}
        mock_client.post.assert_called_once_with(
            f"{self.TEST_BASE_URL}/projects/{self.TEST_PROJECT_REF}/database/query",
            headers=supabase_manager._default_headers,
            json={"query": test_sql},
            timeout=10,
        )

    def test_execute_sql_failure(self, supabase_manager, mock_httpx_client, mocker):
        # Mock
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPError("Test error")
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mock_httpx_client.return_value.__enter__.return_value = mock_client

        # Setup & Assert
        with pytest.raises(httpx.HTTPError):
            supabase_manager.execute_sql("SELECT * FROM test_table;")

    def test_get_session_schemas_success(self, supabase_manager, mock_httpx_client, mocker):
        # Mock
        expected_result = [
            {"table_name": f"test_table_{self.TEST_SESSION_ID}", "columns": "id bigint NOT NULL\ntitle text NOT NULL"}
        ]
        mock_response = mocker.MagicMock()
        mock_response.json.return_value = expected_result
        mock_response.raise_for_status.return_value = None
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mock_httpx_client.return_value.__enter__.return_value = mock_client

        # Exec
        result = supabase_manager.get_session_schemas(
            session_id=self.TEST_SESSION_ID, project_ref=self.TEST_PROJECT_REF
        )

        # Assert
        assert result == expected_result

    def test_get_database_schemas_all_tables(self, supabase_manager, mock_httpx_client, mocker):
        # Mock
        expected_result = [
            {"table_name": "users", "columns": "id bigint NOT NULL\nemail text NOT NULL"},
            {"table_name": "posts", "columns": "id bigint NOT NULL\ntitle text NOT NULL"},
        ]
        mock_response = mocker.MagicMock()
        mock_response.json.return_value = expected_result
        mock_response.raise_for_status.return_value = None
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mock_httpx_client.return_value.__enter__.return_value = mock_client

        # Exec
        result = supabase_manager._get_database_schemas(project_ref=self.TEST_PROJECT_REF)

        # Assert
        assert result == expected_result

    def test_get_database_schemas_with_session_filter(self, supabase_manager, mock_httpx_client, mocker):
        # Mock
        all_tables = [
            {"table_name": f"test_table_{self.TEST_SESSION_ID}", "columns": "id bigint NOT NULL\ntitle text NOT NULL"},
            {"table_name": "other_table", "columns": "id bigint NOT NULL\ntitle text NOT NULL"},
        ]
        mock_response = mocker.MagicMock()
        mock_response.json.return_value = all_tables
        mock_response.raise_for_status.return_value = None
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mock_httpx_client.return_value.__enter__.return_value = mock_client

        # Exec
        result = supabase_manager._get_database_schemas(
            project_ref=self.TEST_PROJECT_REF, session_id=self.TEST_SESSION_ID
        )

        # Assert
        assert len(result) == 1
        assert self.TEST_SESSION_ID in result[0]["table_name"]

    def test_get_database_schemas_failure(self, supabase_manager, mock_httpx_client, mocker):
        # Mock
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPError("Test error")
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mock_httpx_client.return_value.__enter__.return_value = mock_client

        # Setup & Assert
        with pytest.raises(httpx.HTTPError):
            supabase_manager._get_database_schemas()
