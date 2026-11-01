import Link from "next/link";
import { LoginForm } from "./LoginForm";

export default function LoginPage() {
  return (
    <div className="mx-auto mt-16 max-w-sm">
      <div className="card flex flex-col gap-4">
        <div>
          <h1 className="text-xl font-semibold">Intraday Picks</h1>
          <p className="secondary text-sm">Invite-only. Sign in with the email you were invited with.</p>
        </div>
        <LoginForm />
        <p className="text-xs muted">
          First time here? Open the invite email and set a password. <Link className="underline" href="/forgot-password">Forgot password</Link>
        </p>
      </div>
    </div>
  );
}
