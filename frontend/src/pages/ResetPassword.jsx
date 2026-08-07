import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import { CheckCircle2, Loader2 } from "lucide-react";
import AuthLayout from "../layouts/AuthLayout.jsx";
import { Button } from "../components/ui/button.jsx";
import { PasswordInput } from "../components/ui/PasswordInput.jsx";
import { Label } from "../components/ui/label.jsx";
import { resetPassword } from "../services/api.js";

function extractErrorMessage(err) {
  return err?.response?.data?.detail || "Something went wrong. Please try again.";
}

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const fieldVariants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
};

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await resetPassword(token, password);
      setDone(true);
      setTimeout(() => navigate("/login", { replace: true }), 2500);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthLayout title="Invalid reset link" subtitle="This link is missing its reset token">
        <p className="text-sm text-[var(--text-secondary)]">
          The link you followed is incomplete or malformed. Request a new one to continue.
        </p>
        <Link
          to="/forgot-password"
          className="mt-6 block text-center text-sm font-medium text-primary hover:underline"
        >
          Request a new reset link
        </Link>
      </AuthLayout>
    );
  }

  if (done) {
    return (
      <AuthLayout title="Password reset" subtitle="You're all set">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center gap-4 text-center"
        >
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--brand)]/12 text-[var(--brand)]">
            <CheckCircle2 className="h-6 w-6" />
          </span>
          <p className="text-sm text-[var(--text-secondary)]">
            Your password has been reset. Taking you to sign in…
          </p>
        </motion.div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Set a new password" subtitle="Choose a new password for your account">
      <motion.form
        onSubmit={handleSubmit}
        className="space-y-4"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={fieldVariants} className="space-y-1.5">
          <Label htmlFor="password">New password</Label>
          <PasswordInput
            id="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
          />
        </motion.div>
        <motion.div variants={fieldVariants} className="space-y-1.5">
          <Label htmlFor="confirm-password">Confirm password</Label>
          <PasswordInput
            id="confirm-password"
            autoComplete="new-password"
            required
            minLength={8}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Re-enter your new password"
          />
        </motion.div>

        {error && (
          <motion.p
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </motion.p>
        )}

        <motion.div variants={fieldVariants} whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}>
          <Button type="submit" disabled={submitting} className="w-full" size="lg">
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {submitting ? "Resetting…" : "Reset password"}
          </Button>
        </motion.div>
      </motion.form>

      <p className="mt-6 text-center text-sm text-[var(--text-muted)]">
        <Link to="/login" className="font-medium text-primary hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
