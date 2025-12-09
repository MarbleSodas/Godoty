import { Injectable, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, map, tap, catchError, of, BehaviorSubject } from 'rxjs';

export interface AuthUser {
    id: string;
    email: string;
}

export interface CreditPack {
    id: string;
    name: string;
    amount: number;
    price_id: string;
}

export interface Transaction {
    id: string;
    type: 'top_up' | 'usage' | 'bonus' | 'correction';
    amount: number;
    created_at: string;
    metadata?: any;
}

@Injectable({
    providedIn: 'root'
})
export class AuthService {
    private apiUrl = 'http://127.0.0.1:8000/api/auth';

    // State signals
    isAuthenticated = signal(false);
    currentUser = signal<AuthUser | null>(null);
    creditBalance = signal<number | null>(null);
    isLoading = signal(false);

    // Observable for auth status changes
    private authStatusSubject = new BehaviorSubject<boolean>(false);
    authStatus$ = this.authStatusSubject.asObservable();

    constructor(private http: HttpClient) {
        // Check auth status on service init
        this.checkAuthStatus();
    }

    /**
     * Check current authentication status
     */
    checkAuthStatus(): void {
        this.http.get<any>(`${this.apiUrl}/status`).pipe(
            catchError(() => of({ authenticated: false, user: null, balance: null }))
        ).subscribe(response => {
            this.isAuthenticated.set(response.authenticated);
            this.currentUser.set(response.user);
            this.creditBalance.set(response.balance);
            this.authStatusSubject.next(response.authenticated);
        });
    }

    /**
     * Login with email and password
     */
    login(email: string, password: string): Observable<{ success: boolean; error?: string }> {
        this.isLoading.set(true);
        return this.http.post<any>(`${this.apiUrl}/login`, { email, password }).pipe(
            tap(response => {
                if (response.success) {
                    this.isAuthenticated.set(true);
                    this.currentUser.set(response.user);
                    this.creditBalance.set(response.balance);
                    this.authStatusSubject.next(true);
                }
                this.isLoading.set(false);
            }),
            map(response => ({ success: response.success, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                this.isLoading.set(false);
                const message = error.error?.detail || error.message || 'Login failed';
                return of({ success: false, error: message });
            })
        );
    }

    /**
     * Register new account
     */
    signup(email: string, password: string): Observable<{ success: boolean; message?: string; error?: string }> {
        this.isLoading.set(true);
        return this.http.post<any>(`${this.apiUrl}/signup`, { email, password }).pipe(
            tap(() => this.isLoading.set(false)),
            map(response => ({ success: response.success, message: response.message, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                this.isLoading.set(false);
                const message = error.error?.detail || error.message || 'Signup failed';
                return of({ success: false, message: undefined, error: message });
            })
        );
    }

    /**
     * Logout and clear session
     */
    logout(): Observable<void> {
        return this.http.post<any>(`${this.apiUrl}/logout`, {}).pipe(
            tap(() => {
                this.isAuthenticated.set(false);
                this.currentUser.set(null);
                this.creditBalance.set(null);
                this.authStatusSubject.next(false);
            }),
            map(() => undefined),
            catchError(() => {
                // Clear local state even if server fails
                this.isAuthenticated.set(false);
                this.currentUser.set(null);
                this.creditBalance.set(null);
                this.authStatusSubject.next(false);
                return of(undefined);
            })
        );
    }

    /**
     * Refresh credit balance
     */
    refreshBalance(): void {
        if (!this.isAuthenticated()) return;

        this.http.get<any>(`${this.apiUrl}/balance`).pipe(
            catchError(() => of({ balance: null }))
        ).subscribe(response => {
            this.creditBalance.set(response.balance);
        });
    }

    /**
     * Get available credit packs
     */
    getCreditPacks(): Observable<CreditPack[]> {
        return this.http.get<any>(`${this.apiUrl}/credit-packs`).pipe(
            map(response => response.packs || []),
            catchError(() => of([]))
        );
    }

    /**
     * Get transaction history
     */
    getTransactions(limit: number = 20): Observable<Transaction[]> {
        return this.http.get<any>(`${this.apiUrl}/transactions`, { params: { limit: limit.toString() } }).pipe(
            map(response => response.transactions || []),
            catchError(() => of([]))
        );
    }

    /**
     * Create checkout and open in browser
     */
    createCheckout(priceId: string): Observable<{ success: boolean; url?: string; error?: string }> {
        return this.http.post<any>(`${this.apiUrl}/topup`, { price_id: priceId }).pipe(
            map(response => ({ success: response.success, url: response.url, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                const message = error.error?.detail || error.message || 'Failed to create checkout';
                return of({ success: false, url: undefined, error: message });
            })
        );
    }

    /**
     * Check if Supabase is configured
     */
    checkConfigured(): Observable<{ configured: boolean; has_url: boolean; has_key: boolean }> {
        return this.http.get<any>(`${this.apiUrl}/configured`).pipe(
            catchError(() => of({ configured: false, has_url: false, has_key: false }))
        );
    }

    /**
     * Configure Supabase credentials
     */
    configure(supabaseUrl: string, supabaseAnonKey: string): Observable<{ success: boolean; error?: string }> {
        return this.http.post<any>(`${this.apiUrl}/configure`, {
            supabase_url: supabaseUrl,
            supabase_anon_key: supabaseAnonKey
        }).pipe(
            map(response => ({ success: response.success, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                const message = error.error?.detail || error.message || 'Configuration failed';
                return of({ success: false, error: message });
            })
        );
    }

    /**
     * Sign in with OAuth provider (Google, GitHub, Discord)
     */
    signInWithOAuth(provider: string): Observable<{ success: boolean; url?: string; error?: string }> {
        this.isLoading.set(true);
        return this.http.post<any>(`${this.apiUrl}/oauth`, { provider }).pipe(
            tap(() => this.isLoading.set(false)),
            map(response => ({ success: response.success, url: response.url, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                this.isLoading.set(false);
                const message = error.error?.detail || error.message || 'OAuth failed';
                return of({ success: false, url: undefined, error: message });
            })
        );
    }

    /**
     * Send magic link email for passwordless login
     */
    sendMagicLink(email: string): Observable<{ success: boolean; message?: string; error?: string }> {
        this.isLoading.set(true);
        return this.http.post<any>(`${this.apiUrl}/magic-link`, { email }).pipe(
            tap(() => this.isLoading.set(false)),
            map(response => ({ success: response.success, message: response.message, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                this.isLoading.set(false);
                const message = error.error?.detail || error.message || 'Failed to send magic link';
                return of({ success: false, message: undefined, error: message });
            })
        );
    }

    /**
     * Verify OTP token from magic link
     */
    verifyOTP(email: string, token: string): Observable<{ success: boolean; error?: string }> {
        this.isLoading.set(true);
        return this.http.post<any>(`${this.apiUrl}/verify-otp`, { email, token }).pipe(
            tap(response => {
                if (response.success) {
                    this.isAuthenticated.set(true);
                    this.currentUser.set(response.user);
                    this.creditBalance.set(response.balance);
                    this.authStatusSubject.next(true);
                }
                this.isLoading.set(false);
            }),
            map(response => ({ success: response.success, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                this.isLoading.set(false);
                const message = error.error?.detail || error.message || 'OTP verification failed';
                return of({ success: false, error: message });
            })
        );
    }

    /**
     * Handle OAuth callback with tokens
     */
    handleOAuthCallback(accessToken: string, refreshToken: string): Observable<{ success: boolean; error?: string }> {
        this.isLoading.set(true);
        return this.http.post<any>(`${this.apiUrl}/oauth-callback`, {
            access_token: accessToken,
            refresh_token: refreshToken
        }).pipe(
            tap(response => {
                if (response.success) {
                    this.isAuthenticated.set(true);
                    this.currentUser.set(response.user);
                    this.creditBalance.set(response.balance);
                    this.authStatusSubject.next(true);
                }
                this.isLoading.set(false);
            }),
            map(response => ({ success: response.success, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                this.isLoading.set(false);
                const message = error.error?.detail || error.message || 'OAuth callback failed';
                return of({ success: false, error: message });
            })
        );
    }
}
