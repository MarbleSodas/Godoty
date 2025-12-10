"""
Authentication API routes for Godoty.
Provides endpoints for Supabase authentication and credit management.
"""
import asyncio
import json
import logging
import webbrowser
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, AsyncGenerator

from services.supabase_auth import get_supabase_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Request model for login/signup."""
    email: str = Field(..., min_length=5, description="User email address")
    password: str = Field(..., min_length=6, description="User password")


class ConfigureRequest(BaseModel):
    """Request model for Supabase configuration."""
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anon/public key")


@router.post("/login")
async def login(request: LoginRequest):
    """
    Login with email/password.
    
    Returns:
        User info and authentication status.
    """
    auth = get_supabase_auth()
    result = auth.login(request.email, request.password)
    
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "Login failed"))
    
    # Include balance in response
    balance = auth.get_balance()
    result["balance"] = balance
    return result


@router.post("/signup")
async def signup(request: LoginRequest):
    """
    Register new account.
    
    Returns:
        Registration status and any confirmation requirements.
    """
    auth = get_supabase_auth()
    result = auth.signup(request.email, request.password)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Signup failed"))
    
    return result


@router.post("/logout")
async def logout():
    """
    Logout and clear session.
    
    Returns:
        Success status.
    """
    auth = get_supabase_auth()
    auth.logout()
    return {"success": True, "message": "Logged out successfully"}


class OAuthRequest(BaseModel):
    """Request model for OAuth sign-in."""
    provider: str = Field(..., description="OAuth provider: google, github, discord, twitter, apple")
    redirect_to: Optional[str] = Field(None, description="URL to redirect to after auth")


class MagicLinkRequest(BaseModel):
    """Request model for magic link sign-in."""
    email: str = Field(..., min_length=5, description="User email address")


class OTPVerifyRequest(BaseModel):
    """Request model for OTP verification."""
    email: str = Field(..., min_length=5, description="User email address")
    token: str = Field(..., min_length=6, description="OTP token from email")


class OAuthCallbackRequest(BaseModel):
    """Request model for OAuth callback."""
    access_token: Optional[str] = Field(None, description="Access token from OAuth flow")
    refresh_token: Optional[str] = Field(None, description="Refresh token from OAuth flow")
    code: Optional[str] = Field(None, description="PKCE code for exchange")


@router.post("/oauth")
async def oauth_signin(request: OAuthRequest):
    """
    Get OAuth sign-in URL for a provider.
    
    Opens the OAuth flow in external browser.
    
    Args:
        request: OAuth provider name and optional redirect URL.
    
    Returns:
        OAuth URL to open in browser.
    """
    auth = get_supabase_auth()
    logger.info(f"OAuth request: provider={request.provider}, redirect_to={request.redirect_to}")
    print(f"DEBUG: OAuth request: provider={request.provider}, redirect_to={request.redirect_to}")
    result = auth.get_oauth_url(request.provider, request.redirect_to)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "OAuth failed"))
    
    # Open OAuth URL in default browser
    if result.get("url"):
        try:
            webbrowser.open(result["url"])
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")
    
    return result


@router.post("/magic-link")
async def magic_link_signin(request: MagicLinkRequest):
    """
    Send magic link to email for passwordless login.
    
    Args:
        request: Email address.
    
    Returns:
        Success status and instructions.
    """
    auth = get_supabase_auth()
    result = auth.send_magic_link(request.email)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Magic link failed"))
    
    return result


@router.post("/verify-otp")
async def verify_otp(request: OTPVerifyRequest):
    """
    Verify OTP token from magic link or email.
    
    Args:
        request: Email and OTP token.
    
    Returns:
        User info and authentication status.
    """
    auth = get_supabase_auth()
    result = auth.verify_otp(request.email, request.token)
    
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "OTP verification failed"))
    
    # Include balance in response
    balance = auth.get_balance()
    result["balance"] = balance
    return result


@router.post("/oauth-callback")
async def oauth_callback(request: OAuthCallbackRequest):
    """
    Handle OAuth callback with tokens or code.
    
    Called after user completes OAuth flow in browser.
    
    Args:
        request: Access/refresh tokens or PKCE code.
    
    Returns:
        User info and authentication status.
    """
    auth = get_supabase_auth()
    
    if request.code:
        # PKCE Flow
        result = auth.exchange_code_for_session(request.code)
    elif request.access_token and request.refresh_token:
        # Implicit Flow / Fragment
        result = auth.handle_oauth_callback(request.access_token, request.refresh_token)
    else:
        raise HTTPException(status_code=400, detail="Missing auth credentials (code or tokens)")
    
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "OAuth callback failed"))
    
    # Include balance in response
    balance = auth.get_balance()
    result["balance"] = balance
    return result


@router.get("/callback-html")
async def oauth_callback_html(code: str):
    """
    Handle OAuth callback for Desktop flow (returns HTML).
    
    Exchanges code for session and returns a success page.
    The desktop app polls for session changes, so this page just tells
    the user to close the tab.
    """
    auth = get_supabase_auth()
    
    # Exchange code for session (updates singleton state)
    result = auth.exchange_code_for_session(code)
    
    # HTML response to close window
    success = result["success"]
    title = "Login Successful" if success else "Login Failed"
    color = "#4ade80" if success else "#ef4444"
    icon = """<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>""" if success else """<circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line>"""
    message = "You have been successfully authenticated." if success else result.get("error", "Unknown error")
    sub_message = "You can now close this browser window and return to Godoty." if success else "Please try again."

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #1a1e29; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            .container {{ text-align: center; padding: 2rem; background: #262c3b; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); max-width: 400px; }}
            h1 {{ color: {color}; margin-bottom: 1rem; }}
            p {{ color: #9ca3af; margin-bottom: 2rem; }}
            .btn {{ background: #478cbf; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; text-decoration: none; font-weight: 500; font-size: 1rem; transition: background 0.2s; }}
            .btn:hover {{ background: #3a7cae; }}
        </style>
    </head>
    <body>
        <div class="container">
            <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 1rem;">{icon}</svg>
            <h1>{title}</h1>
            <p>{message}</p>
            <p style="font-size: 0.9em;">{sub_message}</p>
            <div id="action-area" style="margin-top: 2rem;">
                <button class="btn" onclick="closeWindow()">Close Tab</button>
            </div>
            <p id="close-hint" style="display: none; font-size: 0.9em; margin-top: 1rem; color: #9ca3af;">
                Auto-close failed. Please close this tab manually.
            </p>
        </div>
        <script>
            function closeWindow() {{
                try {{
                    // Try standard window.close
                    window.close();
                }} catch (e) {{ console.error(e); }}
                
                // Fallback UI immediately if close fails or shortly after
                setTimeout(function() {{
                    var actionArea = document.getElementById('action-area');
                    if (actionArea) {{
                        actionArea.innerHTML = '<p style="color: #9ca3af; font-size: 1.1em;">You may now close this tab.</p>';
                    }}
                    var hint = document.getElementById('close-hint');
                    if (hint) hint.style.display = 'none';
                }}, 500);
            }}

            // Try to close automatically after 3 seconds if successful
            if ({str(success).lower()}) {{
                setTimeout(closeWindow, 3000);
            }}
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/status")
async def auth_status():
    """
    Get current authentication status.
    
    Returns:
        Authentication state, user info, and credit balance.
    """
    auth = get_supabase_auth()
    
    if auth.is_authenticated:
        balance = auth.get_balance()
        return {
            "authenticated": True,
            "user": {
                "id": auth.user_id,
                "email": auth.user_email
            },
            "balance": balance
        }
    
    return {
        "authenticated": False,
        "user": None,
        "balance": None
    }


@router.get("/balance")
async def get_balance():
    """
    Get current credit balance.
    
    Returns:
        Current balance in dollars.
    """
    auth = get_supabase_auth()
    
    if not auth.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    balance = auth.get_balance()
    return {"balance": balance}


@router.get("/transactions")
async def get_transactions(limit: int = 20):
    """
    Get transaction history.
    
    Args:
        limit: Maximum number of transactions to return.
    
    Returns:
        List of transactions with type, amount, and metadata.
    """
    auth = get_supabase_auth()
    
    if not auth.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    transactions = auth.get_transactions(limit=limit)
    return {"transactions": transactions}


@router.post("/configure")
async def configure_supabase(request: ConfigureRequest):
    """
    Configure Supabase credentials.
    
    Args:
        request: Supabase URL and anon key.
    
    Returns:
        Configuration status.
    """
    auth = get_supabase_auth()
    auth.configure(request.supabase_url, request.supabase_anon_key)
    return {"success": True, "message": "Supabase configured successfully"}


@router.get("/configured")
async def check_configured():
    """
    Check if Supabase is configured.
    
    Returns:
        Configuration status.
    """
    auth = get_supabase_auth()
    url = auth.config.get("supabase_url", "")
    key = auth.config.get("supabase_anon_key", "")
    
    return {
        "configured": bool(url and key),
        "has_url": bool(url),
        "has_key": bool(key)
    }

@router.get("/credentials")
async def get_credentials():
    """
    Get Supabase public credentials for frontend client.
    
    Returns:
        Supabase URL and anon key.
    """
    auth = get_supabase_auth()
    return auth.get_credentials()



@router.get("/balance/stream")
async def stream_balance(request: Request):
    """
    Stream credit balance updates via Server-Sent Events.
    
    Uses Supabase Realtime to subscribe to profile changes and
    streams balance updates to the client in real-time.
    
    Returns:
        SSE stream with balance updates.
    """
    auth = get_supabase_auth()
    
    if not auth.is_authenticated or not auth.client:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = auth.user_id
    
    async def balance_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events for balance updates."""
        # Send initial balance
        try:
            balance = auth.get_balance()
            initial_data = json.dumps({"balance": balance, "type": "initial"})
            yield f"data: {initial_data}\n\n"
        except Exception as e:
            logger.error(f"Error getting initial balance: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return
        
        # Poll for balance changes
        # Note: For true realtime, the website uses Supabase Realtime subscriptions
        # which automatically update when credits change. This SSE stream is a fallback
        # for the desktop app where Supabase Realtime integration is more complex.
        # Balance updates happen near-instantly on the website after purchase.
        last_balance = balance
        poll_interval = 5.0  # Poll every 5 seconds (reduced from 2s for efficiency)
        heartbeat_interval = 15.0  # Send heartbeat every 15 seconds
        time_since_heartbeat = 0.0
        
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"Balance stream client disconnected for user {user_id}")
                    break
                
                # Check current balance
                try:
                    current_balance = auth.get_balance()
                    if current_balance != last_balance:
                        last_balance = current_balance
                        update_data = json.dumps({
                            "balance": current_balance,
                            "type": "update"
                        })
                        yield f"data: {update_data}\n\n"
                        time_since_heartbeat = 0.0  # Reset heartbeat timer after data
                except Exception as e:
                    logger.error(f"Error polling balance: {e}")
                
                # Send periodic heartbeat to keep connection alive
                time_since_heartbeat += poll_interval
                if time_since_heartbeat >= heartbeat_interval:
                    yield f": heartbeat\n\n"
                    time_since_heartbeat = 0.0
                
                await asyncio.sleep(poll_interval)
                
        except asyncio.CancelledError:
            logger.info(f"Balance stream cancelled for user {user_id}")
        except Exception as e:
            logger.error(f"Balance stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        balance_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
