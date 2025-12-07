"""
Authentication API routes for Godoty.
Provides endpoints for Supabase authentication and credit management.
"""
import logging
import webbrowser
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

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


class CheckoutRequest(BaseModel):
    """Request model for checkout creation."""
    variant_id: str = Field(..., description="Lemon Squeezy variant ID for credit pack")


# Product variant IDs - Configure these in implementation
CREDIT_PACKS = {
    "starter": {"name": "Starter Pack", "amount": 10.00, "variant_id": ""},
    "pro": {"name": "Pro Pack", "amount": 25.00, "variant_id": ""},
    "premium": {"name": "Premium Pack", "amount": 50.00, "variant_id": ""},
}


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


class MagicLinkRequest(BaseModel):
    """Request model for magic link sign-in."""
    email: str = Field(..., min_length=5, description="User email address")


class OTPVerifyRequest(BaseModel):
    """Request model for OTP verification."""
    email: str = Field(..., min_length=5, description="User email address")
    token: str = Field(..., min_length=6, description="OTP token from email")


class OAuthCallbackRequest(BaseModel):
    """Request model for OAuth callback."""
    access_token: str = Field(..., description="Access token from OAuth flow")
    refresh_token: str = Field(..., description="Refresh token from OAuth flow")


@router.post("/oauth")
async def oauth_signin(request: OAuthRequest):
    """
    Get OAuth sign-in URL for a provider.
    
    Opens the OAuth flow in external browser.
    
    Args:
        request: OAuth provider name.
    
    Returns:
        OAuth URL to open in browser.
    """
    auth = get_supabase_auth()
    result = auth.get_oauth_url(request.provider)
    
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
    Handle OAuth callback with tokens.
    
    Called after user completes OAuth flow in browser.
    
    Args:
        request: Access and refresh tokens from OAuth.
    
    Returns:
        User info and authentication status.
    """
    auth = get_supabase_auth()
    result = auth.handle_oauth_callback(request.access_token, request.refresh_token)
    
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "OAuth callback failed"))
    
    # Include balance in response
    balance = auth.get_balance()
    result["balance"] = balance
    return result


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


@router.get("/credit-packs")
async def get_credit_packs():
    """
    Get available credit packs for purchase.
    
    Returns:
        List of available credit packs with pricing.
    """
    packs = []
    for pack_id, pack_info in CREDIT_PACKS.items():
        if pack_info["variant_id"]:  # Only include configured packs
            packs.append({
                "id": pack_id,
                "name": pack_info["name"],
                "amount": pack_info["amount"],
                "variant_id": pack_info["variant_id"]
            })
    return {"packs": packs}


@router.post("/topup")
async def create_topup(request: CheckoutRequest):
    """
    Create checkout URL and open in external browser.
    
    Args:
        request: Checkout request with variant_id.
    
    Returns:
        Checkout URL for the payment page.
    """
    auth = get_supabase_auth()
    
    if not auth.is_authenticated or not auth.client:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Call Edge Function to create checkout
        response = auth.client.functions.invoke(
            "create-checkout",
            invoke_options={"body": {"variant_id": request.variant_id}}
        )
        
        if isinstance(response, dict) and response.get("url"):
            checkout_url = response["url"]
            # Open in default browser (not webview for payment security)
            try:
                webbrowser.open(checkout_url)
            except Exception as e:
                logger.warning(f"Could not open browser: {e}")
            
            return {"success": True, "url": checkout_url}
        
        raise HTTPException(status_code=500, detail="Failed to create checkout URL")
        
    except Exception as e:
        logger.error(f"Checkout creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
