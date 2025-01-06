from metagpt.tools.tool_registry import register_tool


# An un-implemented tool reserved for deploying a local service to public
@register_tool(include_functions=["deploy_to_public"])
class Deployer:
    """Deploy a service to public."""

    async def static_server(self, src_path: str, proj_name: str) -> str:
        """This function will be implemented in the remote service."""
        return "http://127.0.0.1:8000/index.html"

    async def deploy_to_public(self, dist_dir: str, proj_name: str) -> str:
        """
        Deploy a web project to public. Used only for final deployment, you should NOT use it for development and testing.
        Args:
            dist_dir (str): The dist directory of the web project after run build.
            proj_name (str): Project name to appear in the public URL.
        >>>
            await Deployer().deploy_to_public("dist", "my-proj")
        """
        url = await self.static_server(dist_dir, proj_name)
        return f"Project {proj_name} deployed successfully to: {url}"
