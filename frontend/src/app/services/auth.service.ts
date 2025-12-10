import { Injectable, signal, OnDestroy } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, map, tap, catchError, of, BehaviorSubject } from 'rxjs';
import { createClient, SupabaseClient, RealtimeChannel } from '@supabase/supabase-js';

export interface AuthUser {
    id: string;
    email: string;
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
export class AuthService implements OnDestroy {
    private apiUrl = 'api/auth';

    // State signals
    isAuthenticated = signal(false);
    currentUser = signal<AuthUser | null>(null);
    creditBalance = signal<number | null>(null);
    isLoading = signal(false);

    // Observable for auth status changes
    private authStatusSubject = new BehaviorSubject<boolean>(false);
    authStatus$ = this.authStatusSubject.asObservable();

    // Supabase Client
    private supabase: SupabaseClient | null = null;
    private balanceChannel: RealtimeChannel | null = null;

    constructor(private http: HttpClient) {
        // Check auth status on service init
        this.checkAuthStatus();
    }

    ngOnDestroy(): void {
        this.unsubscribeFromBalance();
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

            // Connect to balance stream if authenticated
            if (response.authenticated) {
                this.initSupabaseAndSubscribe();
            }
        });
    }

    /**
     * Initialize Supabase client and subscribe to balance updates
     */
    private initSupabaseAndSubscribe(): void {
        if (this.supabase) {
            this.subscribeToBalance();
            return;
        }

        // Fetch credentials
        this.http.get<any>(`${this.apiUrl}/credentials`).pipe(
            catchError(() => of(null))
        ).subscribe(creds => {
            if (creds && creds.supabase_url && creds.supabase_anon_key) {
                this.supabase = createClient(creds.supabase_url, creds.supabase_anon_key);
                this.subscribeToBalance();
            }
        });
    }


    /**
     * Subscribe to realtime balance updates using Supabase
     */
    private async subscribeToBalance() {
        if (!this.supabase || !this.currentUser()?.id || this.balanceChannel) {
            return;
        }

        const userId = this.currentUser()!.id;

        try {
            // Subscribe to changes in the profiles table for this user
            this.balanceChannel = this.supabase
                .channel(`public:profiles:id=eq.${userId}`)
                .on(
                    'postgres_changes',
                    {
                        event: 'UPDATE',
                        schema: 'public',
                        table: 'profiles',
                        filter: `id=eq.${userId}`
                    },
                    (payload) => {
                        console.log('Credit balance update received:', payload);
                        if (payload.new && payload.new['credit_balance'] !== undefined) {
                            this.creditBalance.set(parseFloat(payload.new['credit_balance']));
                        }
                    }
                )
                .subscribe((status) => {
                    console.log('Supabase realtime subscription status:', status);
                });

        } catch (error) {
            console.error('Failed to subscribe to balance updates:', error);
        }
    }

    /**
     * Unsubscribe from balance updates
     */
    private async unsubscribeFromBalance() {
        if (this.balanceChannel) {
            await this.supabase?.removeChannel(this.balanceChannel);
            this.balanceChannel = null;
        }
    }


    /**
     * Poll for authentication status (used for Desktop OAuth flow)
     */
    pollAuthStatus(maxAttempts = 600, intervalMs = 500): Observable<boolean> {
        // Poll for 5 minutes (600 * 500ms)
        return new Observable<boolean>(observer => {
            let attempts = 0;
            const poll = () => {
                this.http.get<any>(`${this.apiUrl}/status`).pipe(
                    catchError(() => of({ authenticated: false, user: null, balance: null }))
                ).subscribe({
                    next: (response) => {
                        if (response.authenticated) {
                            // Update local state
                            this.isAuthenticated.set(true);
                            this.currentUser.set(response.user);
                            this.creditBalance.set(response.balance);
                            this.authStatusSubject.next(true);
                            this.initSupabaseAndSubscribe();

                            observer.next(true);
                            observer.complete();
                        } else {
                            attempts++;
                            if (attempts >= maxAttempts) {
                                observer.next(false);
                                observer.complete();
                            } else {
                                setTimeout(poll, intervalMs);
                            }
                        }
                    },
                    error: () => {
                        attempts++;
                        if (attempts >= maxAttempts) {
                            observer.next(false);
                            observer.complete();
                        } else {
                            setTimeout(poll, intervalMs);
                        }
                    }
                });
            };
            poll();
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
                    // Start balance stream for real-time updates
                    this.initSupabaseAndSubscribe();
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
        // Disconnect balance stream before logout
        this.unsubscribeFromBalance();

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
     * Get transaction history
     */
    getTransactions(limit: number = 20): Observable<Transaction[]> {
        return this.http.get<any>(`${this.apiUrl}/transactions`, { params: { limit: limit.toString() } }).pipe(
            map(response => response.transactions || []),
            catchError(() => of([]))
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
    signInWithOAuth(provider: string, redirectTo?: string): Observable<{ success: boolean; url?: string; error?: string }> {
        this.isLoading.set(true);
        const payload: any = { provider };
        if (redirectTo) {
            payload.redirect_to = redirectTo;
        }

        return this.http.post<any>(`${this.apiUrl}/oauth`, payload).pipe(
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
     * Exchange PKCE code for session
     */
    exchangeCode(code: string): Observable<{ success: boolean; error?: string }> {
        this.isLoading.set(true);
        return this.http.post<any>(`${this.apiUrl}/oauth-callback`, { code }).pipe(
            tap(response => {
                if (response.success) {
                    this.isAuthenticated.set(true);
                    this.currentUser.set(response.user);
                    this.creditBalance.set(response.balance);
                    this.authStatusSubject.next(true);
                    // Start balance stream for real-time updates
                    this.initSupabaseAndSubscribe();
                }
                this.isLoading.set(false);
            }),
            map(response => ({ success: response.success, error: undefined })),
            catchError((error: HttpErrorResponse) => {
                this.isLoading.set(false);
                const message = error.error?.detail || error.message || 'Code exchange failed';
                return of({ success: false, error: message });
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
                    // Start balance stream for real-time updates
                    this.initSupabaseAndSubscribe();
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
                    // Start balance stream for real-time updates
                    this.initSupabaseAndSubscribe();
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
