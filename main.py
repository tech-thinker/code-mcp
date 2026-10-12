from app.server import mcp
from app.loader import load_tools
from app.config import settings

def main():
    load_tools()
    mcp.run(transport=settings.protocol, host="0.0.0.0", port=settings.port)

if __name__ == "__main__":
    main()
