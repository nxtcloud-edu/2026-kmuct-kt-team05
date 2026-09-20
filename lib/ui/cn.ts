import clsx, { type ClassValue } from 'clsx';

/** 조건부 className 결합 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
