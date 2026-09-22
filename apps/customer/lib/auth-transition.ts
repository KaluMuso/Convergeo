import type { UseSessionResult } from "@vergeo/auth/use-session";

export type CustomerSession = NonNullable<UseSessionResult["session"]>;

export type CartMergeResolution = {
  accept_price_changes: string[];
  pickup_location_choices: Record<string, string | null>;
  remove_listing_ids: string[];
};

export type AuthTransitionState = {
  session: CustomerSession | null;
  loading: boolean;
  error: unknown;
  generation: number;
};

/** One identity-scoped barrier shared by auth events, navigation, and checkout. */
export class AuthTransition {
  private rawSession: CustomerSession | null = null;
  private pending: Promise<void> | null = null;
  private tail: Promise<void> = Promise.resolve();
  private listeners = new Set<() => void>();
  private state: AuthTransitionState = {
    session: null,
    loading: true,
    error: null,
    generation: 0,
  };

  constructor(
    private readonly reconcile: (
      session: CustomerSession,
      resolution?: CartMergeResolution,
    ) => Promise<void>,
  ) {}

  snapshot = (): AuthTransitionState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private publish(patch: Partial<AuthTransitionState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  failInitialization(error: unknown) {
    this.rawSession = null;
    this.pending = null;
    this.publish({
      session: null,
      loading: false,
      error,
      generation: this.state.generation + 1,
    });
  }

  observe(
    session: CustomerSession | null,
    options: { retry?: boolean; resolution?: CartMergeResolution } = {},
  ): Promise<void> {
    if (!session) {
      this.rawSession = null;
      this.pending = null;
      this.publish({
        session: null,
        loading: false,
        error: null,
        generation: this.state.generation + 1,
      });
      return Promise.resolve();
    }

    const sameIdentity = this.rawSession?.user.id === session.user.id;
    this.rawSession = session;
    if (sameIdentity && !options.retry) {
      if (this.pending) return this.pending;
      if (this.state.error) return Promise.reject(this.state.error);
      if (this.state.session) this.publish({ session });
      return Promise.resolve();
    }

    const generation = this.state.generation + 1;
    this.publish({ session: null, loading: true, error: null, generation });

    // Supabase auth callbacks must return synchronously. Queue the merge outside
    // the callback and serialize identity changes so their cookie-bearing
    // requests cannot overtake each other.
    const work = this.tail
      .catch(() => undefined)
      .then(async () => {
        if (this.state.generation !== generation) throw new Error("auth.transition_changed");
        await this.reconcile(session, options.resolution);
        if (this.state.generation !== generation) throw new Error("auth.transition_changed");
        this.publish({ session: this.rawSession, loading: false, error: null });
      });
    this.pending = work;
    this.tail = work;
    void work.then(
      () => {
        if (this.state.generation === generation) this.pending = null;
      },
      (error: unknown) => {
        if (this.state.generation === generation) {
          this.pending = null;
          this.publish({ session: null, loading: false, error });
        }
      },
    );
    return work;
  }

  async ready(retry = false, resolution?: CartMergeResolution): Promise<CustomerSession | null> {
    if (retry && this.rawSession) {
      await this.observe(this.rawSession, { retry: true, resolution });
    } else if (this.pending) {
      await this.pending;
    }
    if (this.state.error) throw this.state.error;
    return this.state.session;
  }
}
