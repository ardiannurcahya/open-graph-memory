"""MCP stdio server for direct agent integration."""

import asyncio
import json
import os
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.mcp_server import MCPRequest, MCPResponse, handle_mcp_request


class MCPStdioServer:
    def __init__(self, database_url: str, project_id: str, api_key: str) -> None:
        self.engine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        self.project_id = project_id
        self.api_key = api_key

    async def run(self) -> None:
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break

                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                    request = MCPRequest(**data)
                except (json.JSONDecodeError, Exception) as e:
                    error_response = MCPResponse(
                        error={"code": -32700, "message": f"parse error: {str(e)}"}
                    )
                    sys.stdout.write(error_response.model_dump_json() + "\n")
                    sys.stdout.flush()
                    continue

                async with self.session_factory() as session:
                    try:
                        response = await handle_mcp_request(request, self.project_id, session)
                    except Exception as e:
                        response = MCPResponse(
                            id=request.id,
                            error={"code": -32603, "message": f"internal error: {str(e)}"},
                        )

                sys.stdout.write(response.model_dump_json() + "\n")
                sys.stdout.flush()

            except Exception as e:
                error_response = MCPResponse(
                    error={"code": -32603, "message": f"server error: {str(e)}"}
                )
                sys.stdout.write(error_response.model_dump_json() + "\n")
                sys.stdout.flush()


async def run_mcp_stdio(database_url: str, project_id: str, api_key: str) -> None:
    server = MCPStdioServer(database_url, project_id, api_key)
    await server.run()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://localhost/ogm")
    project_id = os.environ.get("OGM_PROJECT_ID", "")
    api_key = os.environ.get("OGM_API_KEY", "")

    if not project_id or not api_key:
        print("OGM_PROJECT_ID and OGM_API_KEY environment variables required", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_mcp_stdio(database_url, project_id, api_key))


if __name__ == "__main__":
    main()
