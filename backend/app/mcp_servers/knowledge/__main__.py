from app.mcp_servers.knowledge.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
