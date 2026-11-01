"use client";

import Link from "next/link";
import { useActionState } from "react";
import { requestReset } from "../login/actions";

export default function ForgotPasswordPage() {
  const [state, action, pending] = useActionState(requestReset, undefined);
  return (
    <div className="mx-auto mt-16 max-w-sm">
      <div className="card flex flex-col gap-4">
        <h1 className="text-xl font-semibold">Reset password</h1>
        {state?.done ? (
          <p className="secondary text-sm">If that address has been invited, a reset link is on its way.</p>
        ) : (
          <form action={action} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Email
              <input className="input" type="email" name="email" autoComplete="email" required />
            </label>
            {state?.error && <p className="text-sm delta-down">{state.error}</p>}
            <button className="btn primary" type="submit" disabled={pending}>
              {pending ? "Sending…" : "Send reset link"}
            </button>
          </form>
        )}
        <Link className="text-xs muted underline" href="/login">Back to sign in</Link>
      </div>
    </div>
  );
}
