import pytest

from metagpt.configs.supabase_config import SupabaseConfig
from metagpt.tools.libs.supabase_manager import SupabaseManager


class TestSupabaseManager:
    TEST_ACCESS_TOKEN = "test_access_token"
    TEST_BASE_URL = "https://api.supabase.com/v1"
    TEST_SESSION_ID = "test_session_123"
    TEST_PROJECT_URL = "test_project_url"
    TEST_PROJECT_KEY = "test_project_key"
    TEST_PROJECT_REF = "test_project_ref"

    @pytest.fixture
    def supabase_config(self):
        return SupabaseConfig(
            enable=True,
            access_token=self.TEST_ACCESS_TOKEN,
            management_base_url=self.TEST_BASE_URL,
            project_ref=self.TEST_PROJECT_REF,
            project_url=self.TEST_PROJECT_URL,
            project_key=self.TEST_PROJECT_KEY,
        )

    @pytest.fixture
    def supabase_manager(self, supabase_config):
        return SupabaseManager(config=supabase_config)

    def test_initialization_with_custom_values(self, supabase_manager):
        # Assert
        assert supabase_manager.config.access_token == self.TEST_ACCESS_TOKEN
        assert supabase_manager.config.management_base_url == self.TEST_BASE_URL
        assert supabase_manager.default_headers == {
            "Authorization": f"Bearer {self.TEST_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

    @pytest.mark.asyncio
    async def test_execute_sql_success(self, supabase_manager, mocker):
        # Mock
        mock_response = {"result": "success"}
        mock_apost = mocker.patch(
            "metagpt.tools.libs.supabase_manager.apost", new_callable=mocker.AsyncMock, return_value=mock_response
        )

        # Setup
        test_sql = "SELECT * FROM test_table;"

        # Exec
        result = await supabase_manager.execute_sql(test_sql, self.TEST_PROJECT_REF)

        # Assert
        assert result == {"result": "success"}
        mock_apost.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_sql_failure(self, supabase_manager, mocker):
        # Mock
        mock_apost = mocker.patch("metagpt.tools.libs.supabase_manager.apost", new_callable=mocker.AsyncMock)
        mock_apost.side_effect = Exception("Test error")

        # Setup & Assert
        with pytest.raises(Exception, match="Test error"):
            await supabase_manager.execute_sql("SELECT * FROM test_table;")

    @pytest.mark.asyncio
    async def test_get_session_schemas_success(self, supabase_manager, mocker):
        # Mock
        expected_result = [
            {"table_name": f"test_table_{self.TEST_SESSION_ID}", "columns": "id bigint NOT NULL\ntitle text NOT NULL"}
        ]
        mock_apost = mocker.patch(
            "metagpt.tools.libs.supabase_manager.apost", new_callable=mocker.AsyncMock, return_value=expected_result
        )

        # Exec
        result = await supabase_manager.get_session_schemas(
            session_id=self.TEST_SESSION_ID, project_ref=self.TEST_PROJECT_REF
        )

        # Assert
        assert result == expected_result
        mock_apost.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_database_schemas_all_tables(self, supabase_manager, mocker):
        # Mock
        expected_result = [
            {"table_name": "users", "columns": "id bigint NOT NULL\nemail text NOT NULL"},
            {"table_name": "posts", "columns": "id bigint NOT NULL\ntitle text NOT NULL"},
        ]
        mock_apost = mocker.patch(
            "metagpt.tools.libs.supabase_manager.apost", new_callable=mocker.AsyncMock, return_value=expected_result
        )

        # Exec
        result = await supabase_manager._get_database_schemas(project_ref=self.TEST_PROJECT_REF)

        # Assert
        assert result == expected_result
        mock_apost.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_database_schemas_with_session_filter(self, supabase_manager, mocker):
        # Mock
        all_tables = [
            {"table_name": f"test_table_{self.TEST_SESSION_ID}", "columns": "id bigint NOT NULL\ntitle text NOT NULL"},
            {"table_name": "other_table", "columns": "id bigint NOT NULL\ntitle text NOT NULL"},
        ]
        mock_apost = mocker.patch(
            "metagpt.tools.libs.supabase_manager.apost", new_callable=mocker.AsyncMock, return_value=all_tables
        )

        # Exec
        result = await supabase_manager._get_database_schemas(
            project_ref=self.TEST_PROJECT_REF, session_id=self.TEST_SESSION_ID
        )

        # Assert
        assert len(result) == 1
        assert self.TEST_SESSION_ID in result[0]["table_name"]
        mock_apost.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_database_schemas_failure(self, supabase_manager, mocker):
        # Mock
        mock_apost = mocker.patch("metagpt.tools.libs.supabase_manager.apost", new_callable=mocker.AsyncMock)
        mock_apost.side_effect = Exception("Test error")

        # Setup & Assert
        with pytest.raises(Exception, match="Test error"):
            await supabase_manager._get_database_schemas(project_ref=self.TEST_PROJECT_REF)
