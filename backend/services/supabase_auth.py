"""
Supabase authentication service for Godoty.
Handles user login/signup, session management, and secure token storage.
"""
import logging
from typing import Optional, Dict, Any

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    Client = None

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

from config_manager import get_config

logger = logging.getLogger(__name__)

SERVICE_NAME = "godoty"


class SupabaseAuth:
    """Manages Supabase authentication and secure token storage."""
    
    def __init__(self):
        self.config = get_config()
        self._client: Optional[Client] = None
        self._user = None
        self._session = None
    
    @property
    def client(self) -> Optional[Client]:
        """Get Supabase client, initializing if needed."""
        if not HAS_SUPABASE:
            logger.warning("supabase-py not installed - auth disabled")
            return None
            
        if not self._client:
            url = self.config.get("supabase_url", "")
            anon_key = self.config.get("supabase_anon_key", "")
            
            if url and anon_key:
                try:
                    self._client = create_client(url, anon_key)
                    # Try to restore session
                    self._restore_session()
                except Exception as e:
                    logger.error(f"Failed to create Supabase client: {e}")
                    
        return self._client
    
    def _store_token(self, key: str, value: str):
        """Securely store token using OS keyring or fallback to config."""
        if HAS_KEYRING:
            try:
                keyring.set_password(SERVICE_NAME, key, value)
                return
            except Exception as e:
                logger.warning(f"Keyring storage failed: {e}")
        # Fallback to config file
        self.config.set(key, value)
    
    def _get_token(self, key: str) -> Optional[str]:
        """Retrieve token from secure storage."""
        if HAS_KEYRING:
            try:
                token = keyring.get_password(SERVICE_NAME, key)
                if token:
                    return token
            except Exception as e:
                logger.debug(f"Keyring retrieval failed: {e}")
        return self.config.get(key)
    
    def _clear_tokens(self):
        """Clear stored tokens."""
        for key in ["supabase_access_token", "supabase_refresh_token"]:
            if HAS_KEYRING:
                try:
                    keyring.delete_password(SERVICE_NAME, key)
                except:
                    pass
            self.config.set(key, "")
    
    def _restore_session(self):
        """Restore session from stored tokens."""
        access_token = self._get_token("supabase_access_token")
        refresh_token = self._get_token("supabase_refresh_token")
        
        if access_token and refresh_token and self._client:
            try:
                # Set session directly
                self._client.auth.set_session(access_token, refresh_token)
                response = self._client.auth.get_user()
                if response and response.user:
                    self._user = response.user
                    self._session = self._client.auth.get_session()
                    logger.info("Session restored successfully")
            except Exception as e:
                logger.warning(f"Session restore failed: {e}")
                self._clear_tokens()
    
    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Login with email/password."""
        if not self.client:
            return {"success": False, "error": "Supabase not configured"}
        
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.session:
                self._store_token("supabase_access_token", response.session.access_token)
                self._store_token("supabase_refresh_token", response.session.refresh_token)
                self._user = response.user
                self._session = response.session
                logger.info(f"User logged in: {email}")
                return {"success": True, "user": {"email": response.user.email, "id": response.user.id}}
            
            return {"success": False, "error": "Login failed"}
        except Exception as e:
            logger.error(f"Login error: {e}")
            return {"success": False, "error": str(e)}
    
    def signup(self, email: str, password: str) -> Dict[str, Any]:
        """Register new user."""
        if not self.client:
            return {"success": False, "error": "Supabase not configured"}
        
        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password
            })
            
            if response.user:
                logger.info(f"User registered: {email}")
                return {"success": True, "message": "Account created. Check email for confirmation if required."}
            
            return {"success": False, "error": "Signup failed"}
        except Exception as e:
            logger.error(f"Signup error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_oauth_url(self, provider: str, redirect_to: str = None) -> Dict[str, Any]:
        """
        Get OAuth sign-in URL for a provider (google, github, discord).
        Returns URL that should be opened in external browser.
        """
        if not self.client:
            return {"success": False, "error": "Supabase not configured"}
        
        valid_providers = ["google", "github", "discord", "twitter", "apple"]
        if provider.lower() not in valid_providers:
            return {"success": False, "error": f"Invalid provider. Use: {', '.join(valid_providers)}"}
        
        try:
            # Get OAuth URL - user will be redirected to provider
            options = {"provider": provider.lower()}
            if redirect_to:
                options["options"] = {"redirect_to": redirect_to}
            
            print(f"DEBUG: Supabase sign_in_with_oauth options: {options}")
            logger.info(f"Supabase sign_in_with_oauth options: {options}")
            
            response = self.client.auth.sign_in_with_oauth(options)
            
            if response and hasattr(response, "url"):
                return {"success": True, "url": response.url}
            
            return {"success": False, "error": "Failed to get OAuth URL"}
        except Exception as e:
            logger.error(f"OAuth URL error: {e}")
            return {"success": False, "error": str(e)}
    
    def send_magic_link(self, email: str, redirect_to: str = None) -> Dict[str, Any]:
        """
        Send a magic link (passwordless) login email.
        User clicks link in email to authenticate.
        """
        if not self.client:
            return {"success": False, "error": "Supabase not configured"}
        
        try:
            options = {"email": email}
            if redirect_to:
                options["options"] = {"email_redirect_to": redirect_to}
            
            self.client.auth.sign_in_with_otp(options)
            logger.info(f"Magic link sent to: {email}")
            return {"success": True, "message": "Check your email for the login link."}
        except Exception as e:
            logger.error(f"Magic link error: {e}")
            return {"success": False, "error": str(e)}
    
    def verify_otp(self, email: str, token: str) -> Dict[str, Any]:
        """
        Verify an OTP token (from magic link or email OTP).
        """
        if not self.client:
            return {"success": False, "error": "Supabase not configured"}
        
        try:
            response = self.client.auth.verify_otp({
                "email": email,
                "token": token,
                "type": "email"
            })
            
            if response.session:
                self._store_token("supabase_access_token", response.session.access_token)
                self._store_token("supabase_refresh_token", response.session.refresh_token)
                self._user = response.user
                self._session = response.session
                logger.info(f"OTP verified for: {email}")
                return {"success": True, "user": {"email": response.user.email, "id": response.user.id}}
            
            return {"success": False, "error": "OTP verification failed"}
        except Exception as e:
            logger.error(f"OTP verification error: {e}")
            return {"success": False, "error": str(e)}
    
    def exchange_code_for_session(self, code: str) -> Dict[str, Any]:
        """
        Exchange PKCE code for session.
        """
        if not self.client:
            return {"success": False, "error": "Supabase not configured"}
        
        try:
            response = self.client.auth.exchange_code_for_session({
                "auth_code": code
            })
            
            if response.session:
                self._store_token("supabase_access_token", response.session.access_token)
                self._store_token("supabase_refresh_token", response.session.refresh_token)
                self._user = response.user
                self._session = response.session
                logger.info(f"Session established via code exchange for: {response.user.email}")
                return {"success": True, "user": {"email": response.user.email, "id": response.user.id}}
            
            return {"success": False, "error": "Code exchange failed to return session"}
        except Exception as e:
            logger.error(f"Code exchange error: {e}")
            return {"success": False, "error": str(e)}

    def handle_oauth_callback(self, access_token: str, refresh_token: str) -> Dict[str, Any]:
        """
        Handle OAuth callback by setting the session from tokens.
        Called after user completes OAuth flow in browser.
        """
        if not self.client:
            return {"success": False, "error": "Supabase not configured"}
        
        try:
            self.client.auth.set_session(access_token, refresh_token)
            response = self.client.auth.get_user()
            
            if response and response.user:
                self._store_token("supabase_access_token", access_token)
                self._store_token("supabase_refresh_token", refresh_token)
                self._user = response.user
                self._session = self.client.auth.get_session()
                logger.info(f"OAuth session set for: {response.user.email}")
                return {"success": True, "user": {"email": response.user.email, "id": response.user.id}}
            
            return {"success": False, "error": "Failed to get user from OAuth tokens"}
        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            return {"success": False, "error": str(e)}
    
    def logout(self):
        """Logout and clear tokens."""
        if self.client:
            try:
                self.client.auth.sign_out()
            except Exception as e:
                logger.debug(f"Logout error: {e}")
        self._clear_tokens()
        self._user = None
        self._session = None
        logger.info("User logged out")
    
    def get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """
        Get current access token for API requests.
        
        Args:
            force_refresh: If True, attempt to refresh the token even if it appears valid.
        
        Returns:
            Current access token or None if not authenticated.
        """
        if not self._client:
            # Try stored token as fallback
            return self._get_token("supabase_access_token")
            
        try:
            # Try to get current session - this should auto-refresh if needed
            session = self._client.auth.get_session()
            
            if session:
                # Update stored tokens if they changed (e.g., after refresh)
                if session.access_token != self._get_token("supabase_access_token"):
                    self._store_token("supabase_access_token", session.access_token)
                    if session.refresh_token:
                        self._store_token("supabase_refresh_token", session.refresh_token)
                    logger.debug("Updated stored tokens after session refresh")
                    
                return session.access_token
            
            # Session is None - try to refresh using stored refresh token
            refresh_token = self._get_token("supabase_refresh_token")
            if refresh_token:
                logger.info("Session expired, attempting to refresh...")
                try:
                    response = self._client.auth.refresh_session(refresh_token)
                    if response.session:
                        self._store_token("supabase_access_token", response.session.access_token)
                        self._store_token("supabase_refresh_token", response.session.refresh_token)
                        self._session = response.session
                        self._user = response.user
                        logger.info("Session refreshed successfully")
                        return response.session.access_token
                except Exception as refresh_error:
                    logger.warning(f"Session refresh failed: {refresh_error}")
                    
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
        
        # Fallback to stored token (may be expired but better than nothing for some cases)
        if self._session:
            return self._session.access_token
            
        return self._get_token("supabase_access_token")
    
    def get_balance(self) -> Optional[float]:
        """Get user's current credit balance."""
        if not self.client or not self._user:
            return None
        try:
            # Use maybeSingle() instead of single() to handle missing profiles gracefully
            response = self.client.table("profiles").select("credit_balance").eq("id", self._user.id).maybe_single().execute()
            if response.data:
                return float(response.data.get("credit_balance", 0))
            # Profile doesn't exist - return 0 but log for debugging
            logger.warning(f"No profile found for user {self._user.id}, returning 0 balance")
            return 0.0
        except Exception as e:
            logger.error(f"Balance fetch error: {e}")
            return None
    
    def get_transactions(self, limit: int = 20) -> list:
        """Get user's transaction history."""
        if not self.client or not self._user:
            return []
        try:
            response = self.client.table("transactions").select("*").eq("user_id", self._user.id).order("created_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Transaction fetch error: {e}")
            return []
    
    @property
    def is_authenticated(self) -> bool:
        """Check if user is logged in."""
        return self._user is not None
    
    @property
    def user_id(self) -> Optional[str]:
        """Get current user ID."""
        return self._user.id if self._user else None
    
    @property
    def user_email(self) -> Optional[str]:
        """Get current user email."""
        return self._user.email if self._user else None
    
    def configure(self, supabase_url: str, supabase_anon_key: str):
        """Configure Supabase credentials."""
        self.config.set("supabase_url", supabase_url)
        self.config.set("supabase_anon_key", supabase_anon_key)
        # Reset client to pick up new config
        self._client = None
        logger.info("Supabase configuration updated")

    def get_credentials(self) -> Dict[str, str]:
        """Get public Supabase credentials."""
        url = self.config.get("supabase_url", "")
        key = self.config.get("supabase_anon_key", "")
        return {
            "supabase_url": url,
            "supabase_anon_key": key
        }

# Singleton instance
_auth_instance = None


def get_supabase_auth() -> SupabaseAuth:
    """Get the global Supabase auth instance."""
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = SupabaseAuth()
    return _auth_instance
