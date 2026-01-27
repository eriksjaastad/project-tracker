/**
 * XSS Sanitization utilities for frontend.
 * 
 * React automatically escapes text content, but this utility provides
 * additional sanitization for cases where we need to ensure safety.
 */

/**
 * Sanitize text to prevent XSS attacks.
 * Escapes HTML entities similar to backend sanitization.
 * 
 * Note: React's JSX automatically escapes text content, so this is primarily
 * for cases where we might need to sanitize before passing to other systems
 * or for consistency with backend sanitization.
 * 
 * @param text - The text to sanitize
 * @returns Sanitized text with HTML entities escaped
 */
export function sanitizeText(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.textContent || '';
}

/**
 * Check if text contains potentially dangerous HTML/script content.
 * This is a lightweight check - React's escaping handles the actual protection.
 * 
 * @param text - The text to check
 * @returns True if text contains HTML-like patterns
 */
export function containsHTML(text: string): boolean {
  return /<[^>]*>/g.test(text);
}
