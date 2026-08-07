import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Loader2 } from "lucide-react";
import AuthLayout from "../layouts/AuthLayout.jsx";
import { Button } from "../components/ui/button.jsx";
import { Input } from "../components/ui/input.jsx";
import { PasswordInput } from "../components/ui/PasswordInput.jsx";
import { Label } from "../components/ui/label.jsx";
import { useAuth } from "../context/AuthContext.jsx";

function extractErrorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (Array.isArray(detail)) return detail[0]?.msg || "Please check your details and try again.";
  return detail || "Something went wrong. Please try again.";
}

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const fieldVariants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
};

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setSubmitting(true);
    try {
      await register(email, password);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Create your account" subtitle="Start organizing your downloads automatically">
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
        <motion.div variants={fieldVariants} className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
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
            {submitting ? "Creating account…" : "Create account"}
          </Button>
        </motion.div>
      </motion.form>

      <p className="mt-6 text-center text-sm text-[var(--text-muted)]">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
