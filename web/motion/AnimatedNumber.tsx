"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion, useSpring, useTransform } from "motion/react";
import { numero } from "../formato";

interface AnimatedNumberProps {
  value: number;
  decimals?: number;
  className?: string;
}

/** Un numero che conta fino al suo valore quando entra in vista, in formato
 *  italiano (12.345,6). `metric` dà le cifre a larghezza fissa: senza, la riga
 *  si sposta a ogni fotogramma. */
export function AnimatedNumber({ value, decimals = 0, className }: AnimatedNumberProps) {
  const shouldReduce = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);

  const spring = useSpring(0, { stiffness: 110, damping: 22 });
  const rounded = useTransform(spring, (current) => numero(current, decimals));

  useEffect(() => {
    if (shouldReduce) return;
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.1 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [shouldReduce]);

  useEffect(() => {
    if (visible) spring.set(value);
  }, [value, visible, spring]);

  const classe = className ? `metric ${className}` : "metric";
  if (shouldReduce) return <span className={classe}>{numero(value, decimals)}</span>;
  return (
    <motion.span ref={ref} className={classe}>
      {rounded}
    </motion.span>
  );
}
