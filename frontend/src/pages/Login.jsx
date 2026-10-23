import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Loader2 } from "lucide-react";
import AuthLayout from "../layouts/AuthLayout.jsx";
import { Button } from "../components/ui/button.jsx";
import { Input } from "../components/ui/input.jsx";
import { PasswordInput } from "../components/ui/PasswordInput.jsx";
import { Label } from "../components/ui/label.jsx";
import { useAuth } from "../context/AuthContext.jsx";

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

export default function Login() {
  const { login, verifyTwoFactor } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [pendingToken, setPendingToken] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const redirectTo = location.state?.from?.pathname || "/app";

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.requires_2fa) {
        setPendingToken(result.pending_token);
      } else {
        navigate(redirectTo, { replace: true });
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerifyCode(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await verifyTwoFactor(pendingToken, code.trim());
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (pendingToken) {
    return (
      <AuthLayout
        eyebrow="Two-factor authentication"
        title="Enter your code"
        subtitle="Open your authenticator app, or use a backup code"
      >
        <motion.form
          onSubmit={handleVerifyCode}
          className="auth-fields space-y-4"
          variants={containerVariants}
          initial="hidden"
          animate="show"
        >
          <motion.div variants={fieldVariants} className="space-y-1.5">
            <Label htmlFor="code">Verification code</Label>
            <Input
              id="code"
              autoComplete="one-time-code"
              autoFocus
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
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
              {submitting ? "Verifying…" : "Verify"}
            </Button>
          </motion.div>
          <button
            type="button"
            onClick={() => {
              setPendingToken(null);
              setCode("");
              setError("");
            }}
            className="w-full text-center text-sm text-[var(--text-muted)] hover:underline"
          >
            Back to sign in
          </button>
        </motion.form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout eyebrow="Sign in" title="Open your workspace">
      <motion.form
        onSubmit={handleSubmit}
        className="auth-fields space-y-4"
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
            placeholder="tirth@example.com"
          />
        </motion.div>
        <motion.div variants={fieldVariants} className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link to="/forgot-password" className="text-xs font-medium text-primary hover:underline">
              Forgot password?
            </Link>
          </div>
          <PasswordInput
            id="password"
            showText
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
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
          <Button type="submit" disabled={submitting} className="auth-submit w-full" size="lg">
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </motion.div>
      </motion.form>

      <p className="mt-6 text-center text-sm text-[var(--text-muted)]">
        New to FileFlow?{" "}
        <Link to="/register" className="font-medium text-primary hover:underline">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}
