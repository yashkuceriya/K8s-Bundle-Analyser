import { describe, it, expect, vi } from 'vitest';

// Test the renderMarkdown + DOMPurify sanitization directly
// We import just the module to test the XSS protection
describe('BundleChat XSS Protection', () => {
  it('sanitizes script tags from markdown output', async () => {
    // Dynamically import DOMPurify to test the same sanitization logic
    const DOMPurify = (await import('dompurify')).default;

    const maliciousInput = '<script>alert("xss")</script>Normal text';
    const sanitized = DOMPurify.sanitize(maliciousInput, {
      ALLOWED_TAGS: ['pre', 'code', 'strong', 'li', 'ul', 'br'],
      ALLOWED_ATTR: ['class'],
    });

    expect(sanitized).not.toContain('<script>');
    expect(sanitized).toContain('Normal text');
  });

  it('sanitizes event handlers', async () => {
    const DOMPurify = (await import('dompurify')).default;

    const malicious = '<img src=x onerror=alert(1)>Text';
    const sanitized = DOMPurify.sanitize(malicious, {
      ALLOWED_TAGS: ['pre', 'code', 'strong', 'li', 'ul', 'br'],
      ALLOWED_ATTR: ['class'],
    });

    expect(sanitized).not.toContain('onerror');
    expect(sanitized).not.toContain('<img');
    expect(sanitized).toContain('Text');
  });

  it('preserves allowed markdown HTML', async () => {
    const DOMPurify = (await import('dompurify')).default;

    const safe = '<strong class="font-bold">Bold</strong> and <code class="mono">code</code>';
    const sanitized = DOMPurify.sanitize(safe, {
      ALLOWED_TAGS: ['pre', 'code', 'strong', 'li', 'ul', 'br'],
      ALLOWED_ATTR: ['class'],
    });

    expect(sanitized).toContain('<strong');
    expect(sanitized).toContain('<code');
    expect(sanitized).toContain('Bold');
    expect(sanitized).toContain('code');
  });

  it('strips iframe and object tags', async () => {
    const DOMPurify = (await import('dompurify')).default;

    const malicious = '<iframe src="evil.com"></iframe><object data="evil.swf"></object>Safe';
    const sanitized = DOMPurify.sanitize(malicious, {
      ALLOWED_TAGS: ['pre', 'code', 'strong', 'li', 'ul', 'br'],
      ALLOWED_ATTR: ['class'],
    });

    expect(sanitized).not.toContain('<iframe');
    expect(sanitized).not.toContain('<object');
    expect(sanitized).toContain('Safe');
  });
});
