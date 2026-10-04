import { motion, useReducedMotion } from "framer-motion";
import "./SplashScreen.css";

/** The brand stays still while loading, then gently lifts away when content is ready. */
export default function SplashScreen() {
  const reduceMotion = useReducedMotion();

  return (
    <motion.main
      className="splash-screen"
      role="status"
      aria-label="Loading Dine&Dash"
      aria-busy="true"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ type: "tween", duration: reduceMotion ? 0 : 0.3, ease: "easeInOut" }}
    >
      <motion.span
        className="splash-wordmark"
        initial={false}
        exit={{ y: reduceMotion ? 0 : -8, scale: reduceMotion ? 1 : 1.025 }}
        transition={{ type: "tween", duration: reduceMotion ? 0 : 0.3, ease: "easeInOut" }}
      >
        Dine&amp;Dash
      </motion.span>
    </motion.main>
  );
}
