"use client";

import { useActionState } from "react";
import { setPassword } from "./actions";

export default function SetPasswordPage() {
  const [state, action, pending] = useActionState(setPassword, undefined);
  return (
    <div className="mx-auto mt-16 max-w-sm">
      <div className="card flex flex-col gap-4">
        <div>
          <h1 className="text-xl font-semibold">Choose a password</h1>
          <p className="secondary text-sm">You are signed in through your invite link. Set a password to use next time.</p>
        </div>
        <form action={action} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            New password
            <input className="input" type="password" name="password" autoComplete="new-password" minLength={10} required />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Repeat password
            <input className="input" type="password" name="confirm" autoComplete="new-password" minLength={10} required />
          </label>
          {state?.error && <p className="text-sm delta-down">{state.error}</p>}
          <button className="btn primary" type="submit" disabled={pending}>
            {pending ? "Saving…" : "Save and continue"}
          </button>
        </form>
      </div>
    </div>
  );
}
