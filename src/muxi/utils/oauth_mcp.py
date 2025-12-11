#!/usr/bin/env python3
"""
OAuth Token Grabber for MCP Servers

Standalone utility to handle OAuth authentication flow for MCP servers.
Captures OAuth tokens that can be used with bearer authentication.

Usage:
    python src/muxi/utils/oauth_mcp.py https://mcp.server.com/sse
"""

import sys
import json
import time
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, urlencode, urljoin
from typing import Optional, Dict, Any, cast
import argparse
import urllib.request
import urllib.error

# MUXI logo for OAuth providers that support it
MUXI_LOGO_URL = "https://raw.githubusercontent.com/muxi-ai/.github/refs/heads/main/profile/logo.png"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""

    def do_GET(self) -> None:
        """Handle GET request from OAuth callback."""
        # Parse the URL to extract token or code
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        # Cast server to our custom type for attribute access
        server = cast(OAuthHTTPServer, self.server)

        # Check for access token in query params (implicit flow)
        if "access_token" in query_params:
            server.oauth_token = query_params["access_token"][0]
            server.token_type = "access_token"
            self.send_success_response()
            return

        # Check for access token in fragment (also implicit flow)
        # Note: Fragment is not sent to server, so we'll handle this client-side
        if parsed.fragment:
            fragment_params = parse_qs(parsed.fragment)
            if "access_token" in fragment_params:
                server.oauth_token = fragment_params["access_token"][0]
                server.token_type = "access_token"
                self.send_success_response()
                return

        # Check for authorization code (authorization code flow)
        if "code" in query_params:
            server.oauth_token = query_params["code"][0]
            server.token_type = "authorization_code"
            self.send_success_response()
            return

        # Check for error
        if "error" in query_params:
            error = query_params["error"][0]
            error_desc = query_params.get("error_description", ["Unknown error"])[0]
            server.oauth_error = f"{error}: {error_desc}"
            self.send_error_response(error_desc)
            return

        # If we get here, send a page with JavaScript to extract fragment
        self.send_fragment_extractor()

    def send_success_response(self) -> None:
        """Send success response to browser."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Success - MUXI</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                       display: flex; align-items: center; justify-content: center; height: 100vh;
                       margin: 0; background: #f5f5f5; }}
                .container {{ text-align: center; padding: 40px; background: white;
                            border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #2ecc71; margin-bottom: 20px; }}
                p {{ color: #666; margin-bottom: 30px; }}
                .logo {{ width: 80px; height: 80px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <img src="{logo}" alt="MUXI" class="logo" onerror="this.style.display='none'">
                <h1>✅ Authorization Successful!</h1>
                <p>You can now close this window and return to your terminal.</p>
                <script>window.setTimeout(function(){{{{window.close();}}}}, 2000);</script>
            </div>
        </body>
        </html>
        """.format(
            logo=MUXI_LOGO_URL
        )

        self.wfile.write(html.encode())

    def send_error_response(self, error_message: str) -> None:
        """Send error response to browser."""
        self.send_response(400)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Error - MUXI</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                       display: flex; align-items: center; justify-content: center; height: 100vh;
                       margin: 0; background: #f5f5f5; }}
                .container {{ text-align: center; padding: 40px; background: white;
                            border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #e74c3c; margin-bottom: 20px; }}
                p {{ color: #666; }}
                .logo {{ width: 80px; height: 80px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <img src="{logo}" alt="MUXI" class="logo" onerror="this.style.display='none'">
                <h1>❌ Authorization Failed</h1>
                <p>Error: {error}</p>
            </div>
        </body>
        </html>
        """.format(
            logo=MUXI_LOGO_URL, error=error_message
        )

        self.wfile.write(html.encode())

    def send_fragment_extractor(self) -> None:
        """Send JavaScript to extract token from fragment."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Processing OAuth Response - MUXI</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                       display: flex; align-items: center; justify-content: center; height: 100vh;
                       margin: 0; background: #f5f5f5; }}
                .container {{ text-align: center; padding: 40px; background: white;
                            border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .logo {{ width: 80px; height: 80px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <img src="{logo}" alt="MUXI" class="logo" onerror="this.style.display='none'">
                <h2>Processing OAuth Response...</h2>
            </div>
            <script>
                // Extract token from fragment and redirect
                if (window.location.hash) {{
                    var params = new URLSearchParams(window.location.hash.substring(1));
                    var token = params.get('access_token');
                    if (token) {{
                        // Redirect to callback with token in query params
                        window.location.href = '/callback?access_token=' + encodeURIComponent(token);
                    }} else {{
                        window.location.href = '/callback?error=no_token_found';
                    }}
                }} else {{
                    window.location.href = '/callback?error=no_fragment';
                }}
            </script>
        </body>
        </html>
        """.format(
            logo=MUXI_LOGO_URL
        )

        self.wfile.write(html.encode())

    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP logging."""
        pass


class OAuthHTTPServer(HTTPServer):
    """Custom HTTP server with OAuth state tracking."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.oauth_token: Optional[str] = None
        self.oauth_error: Optional[str] = None
        self.token_type: Optional[str] = None
        self.oauth_config: Optional[Dict[str, Any]] = None
        self.client_info: Optional[Dict[str, Any]] = None
        self.code_verifier: Optional[str] = None


def find_available_port():
    """Find an available port for the callback server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def start_callback_server():
    """Start the OAuth callback server."""
    port = find_available_port()
    server = OAuthHTTPServer(("localhost", port), OAuthCallbackHandler)

    # Start server in a thread
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    return server, port


def exchange_code_for_token(code, oauth_config, client_info, callback_port, code_verifier=None):
    """Exchange authorization code for access token."""
    token_endpoint = oauth_config.get("token_endpoint")
    if not token_endpoint:
        return None

    print("\n🔄 Exchanging authorization code for access token...")

    params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": f"http://localhost:{callback_port}/callback",
    }

    # Add client_id
    if client_info and "client_id" in client_info:
        params["client_id"] = client_info["client_id"]

    # Add PKCE verifier if we have one
    if code_verifier:
        params["code_verifier"] = code_verifier

    # Add client secret if we have one (from dynamic registration)
    if client_info and "client_secret" in client_info:
        params["client_secret"] = client_info["client_secret"]

    try:
        data = urlencode(params).encode()
        req = urllib.request.Request(
            token_endpoint, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                token_response = json.loads(response.read().decode())
                print("✅ Token exchange successful")
                return token_response.get("access_token")
    except Exception as e:
        print(f"❌ Token exchange failed: {e}")
        return None


def wait_for_token(server, timeout=300):
    """Wait for OAuth token with timeout."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        if server.oauth_token:
            # If we got a code, exchange it for a token
            if server.token_type == "authorization_code":
                if hasattr(server, "oauth_config"):
                    token = exchange_code_for_token(
                        server.oauth_token,
                        server.oauth_config,
                        server.client_info,
                        server.server_address[1],
                        getattr(server, "code_verifier", None),
                    )
                    if token:
                        return token, "access_token"
                    else:
                        # Return the code if exchange failed
                        return server.oauth_token, server.token_type
            return server.oauth_token, server.token_type
        if server.oauth_error:
            raise Exception(f"OAuth error: {server.oauth_error}")
        time.sleep(0.1)

    raise TimeoutError("OAuth callback timeout - no response received")


def discover_oauth_config(mcp_url, debug=False):
    """Discover OAuth configuration from MCP server."""
    # Parse base URL
    parsed = urlparse(mcp_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    provider_name = parsed.netloc.lower()

    # First, check if the server requires OAuth by making a test request
    requires_oauth = False
    realm_value = None

    try:
        req = urllib.request.Request(mcp_url)
        req.add_header("Accept", "text/event-stream")
        req.add_header("User-Agent", "muxi-mcp-oauth/1.0")

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                # No auth required
                if debug:
                    print("✅ MCP server accessible without authentication")
                return None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Check WWW-Authenticate header
                auth_header = e.headers.get("WWW-Authenticate", "")
                if "Bearer" in auth_header and "realm=" in auth_header:
                    requires_oauth = True
                    # Extract realm
                    import re

                    realm_match = re.search(r'realm="([^"]+)"', auth_header)
                    if not realm_match:
                        realm_match = re.search(r"realm=(\S+)", auth_header)
                    if realm_match:
                        realm_value = realm_match.group(1)
                        if debug:
                            print(f"🔐 OAuth required, realm: {realm_value}")
    except Exception as e:
        if debug:
            print(f"⚠️  Error checking server: {e}")

    # If no OAuth required, return None
    if not requires_oauth:
        return None

    # Check if realm is a URL (RFC 9728 compliant)
    if realm_value and realm_value.startswith(("http://", "https://")):
        try:
            # Fetch protected resource metadata
            req = urllib.request.Request(realm_value)
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    metadata = json.loads(response.read().decode())
                    auth_server = metadata.get("authorization_servers", [None])[0]
                    if auth_server:
                        # Fetch auth server metadata
                        auth_metadata_url = f"{auth_server}/.well-known/oauth-authorization-server"
                        req = urllib.request.Request(auth_metadata_url)
                        req.add_header("Accept", "application/json")

                        with urllib.request.urlopen(req, timeout=10) as response:
                            if response.status == 200:
                                return json.loads(response.read().decode())
        except Exception as e:
            if debug:
                print(f"⚠️  Error fetching OAuth metadata: {e}")

    # Try well-known endpoint at base URL
    well_known_url = urljoin(base_url, "/.well-known/oauth-authorization-server")
    try:
        req = urllib.request.Request(well_known_url)
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                config = json.loads(response.read().decode())
                print("✅ Found OAuth configuration at well-known endpoint")
                return config
    except Exception:
        pass

    # If we get here, we know OAuth is required but can't discover the configuration
    # Use generic OAuth endpoints based on common patterns
    print("⚠️  OAuth required but configuration not discoverable")
    print(f"   Using generic OAuth endpoints for {provider_name}")

    # Common OAuth endpoint patterns
    generic_config = {
        "provider": provider_name,
        "authorization_endpoint": None,
        "token_endpoint": None,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "generic": True,
    }

    # Try common OAuth patterns
    common_patterns = [
        # Pattern 1: OAuth subdomain
        {
            "auth": f"https://oauth.{parsed.netloc}/authorize",
            "token": f"https://oauth.{parsed.netloc}/token",
        },
        # Pattern 2: Auth subdomain
        {
            "auth": f"https://auth.{parsed.netloc}/authorize",
            "token": f"https://auth.{parsed.netloc}/oauth/token",
        },
        # Pattern 3: OAuth2 subdomain
        {
            "auth": f"https://oauth2.{parsed.netloc}/oauth2/auth",
            "token": f"https://oauth2.{parsed.netloc}/oauth2/token",
        },
        # Pattern 4: Same domain with paths
        {"auth": f"{base_url}/oauth/authorize", "token": f"{base_url}/oauth/token"},
        # Pattern 5: API subdomain
        {
            "auth": f"https://api.{parsed.netloc}/oauth/authorize",
            "token": f"https://api.{parsed.netloc}/oauth/token",
        },
    ]

    # Test which pattern might work (just check if auth endpoint exists)
    for pattern in common_patterns:
        try:
            req = urllib.request.Request(pattern["auth"])
            req.add_header("User-Agent", "muxi-mcp-oauth/1.0")
            with urllib.request.urlopen(req, timeout=2) as response:
                # If we get any response (even error), the endpoint exists
                generic_config["authorization_endpoint"] = pattern["auth"]
                generic_config["token_endpoint"] = pattern["token"]
                print(f"   Found probable endpoints: {pattern['auth']}")
                break
        except Exception:
            continue

    # If no patterns worked, provide instructions
    if not generic_config["authorization_endpoint"]:
        generic_config["note"] = (
            f"Could not determine OAuth endpoints for {provider_name}. "
            "You may need to check their documentation."
        )
        generic_config["requires_client_id"] = True

    return generic_config


def register_oauth_client(config, callback_port):
    """Register OAuth client dynamically if supported."""
    if not config or "registration_endpoint" not in config:
        return None

    print("📝 Attempting dynamic client registration...")

    client_metadata = {
        "client_name": "MUXI Runtime",
        "logo_uri": MUXI_LOGO_URL,
        "redirect_uris": [f"http://localhost:{callback_port}/callback"],
        "grant_types": ["authorization_code", "implicit"],
        "response_types": ["code", "token"],
        "scope": "read write",
    }

    try:
        req = urllib.request.Request(
            config["registration_endpoint"],
            data=json.dumps(client_metadata).encode(),
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status in [200, 201]:
                client_info = json.loads(response.read().decode())
                print("✅ Client registered successfully")
                print(f"   Client ID: {client_info.get('client_id', 'N/A')}")
                return client_info
    except Exception as e:
        print(f"⚠️  Dynamic registration failed: {e}")

    return None


def build_authorization_url(oauth_config, client_info, callback_port):
    """Build the authorization URL from OAuth config and client info."""
    auth_endpoint = oauth_config.get("authorization_endpoint")
    if not auth_endpoint:
        raise ValueError("No authorization endpoint found")

    # Check supported response types
    supported_types = oauth_config.get("response_types_supported", ["code", "token"])

    # Use authorization code flow if that's all that's supported
    if "token" in supported_types:
        response_type = "token"
    else:
        response_type = "code"

    # Default scope
    scope = oauth_config.get("scopes", ["read", "write"])
    if isinstance(scope, list):
        scope = " ".join(scope)

    params = {
        "response_type": response_type,
        "redirect_uri": f"http://localhost:{callback_port}/callback",
        "scope": scope,
    }

    # Add PKCE if using code flow and supported
    if response_type == "code" and "S256" in oauth_config.get(
        "code_challenge_methods_supported", []
    ):
        # Generate PKCE challenge
        import secrets
        import hashlib
        import base64

        code_verifier = (
            base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
        )
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
            .decode("utf-8")
            .rstrip("=")
        )
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
        # Store verifier for later
        params["_code_verifier"] = code_verifier

    # Add client_id if we have it
    if client_info and "client_id" in client_info:
        params["client_id"] = client_info["client_id"]
    else:
        # Some servers might not require client_id for public clients
        params["client_name"] = "MUXI Runtime"

    # Build URL
    parsed = urlparse(auth_endpoint)
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    # Don't include internal params in URL
    url_params = {k: [v] for k, v in params.items() if not k.startswith("_")}
    query_params.update(url_params)

    new_query = urlencode(query_params, doseq=True)
    auth_url = parsed._replace(query=new_query).geturl()

    return auth_url, params.get("_code_verifier")


def display_usage(token):
    """Display token and usage instructions."""
    print("\n" + "=" * 60)
    print("🔑 Your access token:")
    print("=" * 60)
    print(token)
    print("=" * 60)

    print("\n📝 To use this token in your MCP configuration:\n")
    print("1. Add the token as a secret:")
    print("   cd /path/to/formation")
    print(f'   python -m muxi.utils.add_secret MCP_TOKEN "{token}"')

    print("\n2. Configure your MCP server (mcp/server.afs):")
    print("   auth:")
    print('     type: "bearer"')
    print('     token: "${{ secrets.MCP_TOKEN }}"')
    print("\n" + "=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OAuth token grabber for MCP servers",
        epilog="""
Example:
  %(prog)s https://mcp.linear.app/sse
  %(prog)s https://mcp.asana.com/sse
  %(prog)s "https://provider.com/oauth/authorize?client_id=123&response_type=token"
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="MCP server URL or OAuth authorization URL")
    parser.add_argument(
        "--timeout", type=int, default=300, help="Timeout in seconds (default: 300)"
    )
    parser.add_argument("--client-id", help="Use specific client ID (skip dynamic registration)")
    parser.add_argument("--debug", action="store_true", help="Show debug information")

    args = parser.parse_args()

    print("🔐 MCP OAuth Token Grabber")
    print("=" * 60)

    try:
        # Start callback server
        print("📡 Starting local callback server...")
        server, port = start_callback_server()
        print(f"✅ Server running on port {port}")

        # Check if this is a direct OAuth URL or MCP server URL
        if "oauth" in args.url or "authorize" in args.url:
            # Direct OAuth URL provided
            print("\n🔗 Using provided OAuth authorization URL")
            auth_url = args.url
            # Update with our callback port
            parsed = urlparse(auth_url)
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            query_params["redirect_uri"] = [f"http://localhost:{port}/callback"]
            new_query = urlencode(query_params, doseq=True)
            auth_url = parsed._replace(query=new_query).geturl()
        else:
            # MCP server URL - discover OAuth config
            print(f"\n🔍 Checking MCP server: {args.url}")

            # Discover OAuth configuration
            oauth_config = discover_oauth_config(args.url, args.debug)

            if not oauth_config:
                print("\n✅ This MCP server does not require authentication")
                server.shutdown()
                return

            if args.debug:
                print(f"\n📋 OAuth Config: {json.dumps(oauth_config, indent=2)}")

            # Check for provider-specific notes
            if "note" in oauth_config:
                print(f"\n📌 Note: {oauth_config['note']}")

            # Check if we couldn't determine endpoints
            if not oauth_config.get("authorization_endpoint"):
                print("\n❌ Could not determine OAuth endpoints")
                print("   Please check the provider's documentation for:")
                print("   • OAuth authorization URL")
                print("   • Required client registration")
                print("   • Supported authentication flows")
                server.shutdown()
                return

            # For generic configs, require client_id
            if oauth_config.get("generic") and not args.client_id:
                print("\n❌ This provider requires a pre-registered OAuth app")
                print("   1. Register an OAuth app with the provider")
                print("   2. Set callback URL to: http://localhost/callback")
                print("   3. Run again with: --client-id YOUR_CLIENT_ID")
                server.shutdown()
                return

            # Try dynamic client registration or use provided client ID
            if args.client_id:
                print(f"\n🔑 Using provided client ID: {args.client_id}")
                client_info = {"client_id": args.client_id}
            else:
                client_info = register_oauth_client(oauth_config, port)

            # Build authorization URL
            auth_url, code_verifier = build_authorization_url(oauth_config, client_info, port)

            # Store OAuth config and verifier for potential code exchange
            server.oauth_config = oauth_config
            server.client_info = client_info
            server.code_verifier = code_verifier

        # Open browser
        print("\n🌐 Opening browser for authorization...")
        print(f"   URL: {auth_url}")
        webbrowser.open(auth_url)

        # Wait for callback
        print("\n⏳ Waiting for OAuth callback...")
        token, token_type = wait_for_token(server, timeout=args.timeout)

        # Success!
        print("\n✅ Authorization successful!")

        if token_type == "authorization_code":
            print("\n⚠️  Note: Received authorization code (not access token)")
            print("   You may need to exchange this code for an access token")
            print("   Check your OAuth provider's documentation")

        # Display usage
        display_usage(token)

        # Shutdown server
        server.shutdown()

    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
