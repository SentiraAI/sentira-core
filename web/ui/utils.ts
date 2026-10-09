import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Classi Tailwind condizionali, con le ultime che vincono sui conflitti. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
