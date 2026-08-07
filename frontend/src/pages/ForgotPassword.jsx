import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { Loader2, MailCheck } from "lucide-react";
import AuthLayout from "../layouts/AuthLayout.jsx";
import { Button } from "../components/ui/button.jsx";
import { Input } from "../components/ui/input.jsx";
import { Label } from "../components/ui/label.jsx";
import { forgotPassword } from "../services/api.js";

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

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <AuthLayout title="Check your email" subtitle="We've sent password reset instructions">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center gap-4 text-center"
        >
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--brand)]/12 text-[var(--brand)]">
            <MailCheck className="h-6 w-6" />
          </span>
          <p className="text-sm text-[var(--text-secondary)]">
            If an account exists for <span className="font-medium text-[var(--text-primary)]">{email}</span>,
            a link to reset your password is on its way. It'll expire soon, so use it promptly.
          </p>
          <Link to="/login" className="text-sm font-medium text-primary hover:underline">
            Back to sign in
          </Link>
        </motion.div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Forgot your password?" subtitle="Enter your email and we'll send you a reset link">
      <motion.form
        onSubmit={handleSubmit}
        className="space-y-4"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={fieldVariants} className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
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
            {submitting ? "Sending…" : "Send reset link"}
          </Button>
        </motion.div>
      </motion.form>

      <p className="mt-6 text-center text-sm text-[var(--text-muted)]">
        Remembered your password?{" "}
        <Link to="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
