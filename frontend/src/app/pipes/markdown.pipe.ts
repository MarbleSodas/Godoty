import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';
import Prism from 'prismjs';

// Import common languages
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-json';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-css';
import 'prismjs/components/prism-scss';
import 'prismjs/components/prism-gdscript'; // Important for Godot users!

@Pipe({
    name: 'markdown',
    standalone: true
})
export class MarkdownPipe implements PipeTransform {

    constructor(private sanitizer: DomSanitizer) {
        this.configureMarked();
    }

    private configureMarked() {
        const renderer = new marked.Renderer();

        // Custom Code Block Renderer
        renderer.code = ({ text, lang }) => {
            const language = lang || 'text';
            let highlighted = text;

            try {
                if (Prism.languages[language]) {
                    highlighted = Prism.highlight(text, Prism.languages[language], language);
                }
            } catch (e) {
                console.warn(`Failed to highlight ${language}:`, e);
            }

            // Escape code for the data attribute to be safe
            // Actually, we won't put the code in data attribute to avoid massive DOM
            // We will rely on DOM traversal in the click handler

            return `
        <div class="group relative my-4 rounded-lg bg-[#1e1e1e] overflow-hidden border border-[#3b4458]">
          <div class="flex items-center justify-between px-3 py-1.5 bg-[#2d3546] border-b border-[#3b4458] text-xs text-gray-400 font-sans select-none">
             <span class="font-mono text-[#478cbf]">${language}</span>
             <button class="copy-btn hover:text-white transition-colors flex items-center gap-1.5 opacity-70 hover:opacity-100 cursor-pointer p-0.5 rounded focus:outline-none focus:ring-1 focus:ring-[#478cbf]" title="Copy code">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-3.5 h-3.5 pointer-events-none">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.402.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.21.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
                </svg>
                <span class="pointer-events-none">Copy</span>
             </button>
          </div>
          <pre class="!m-0 !p-3 !bg-[#1e1e1e] overflow-x-auto text-sm leading-relaxed"><code class="language-${language}">${highlighted}</code></pre>
        </div>
      `;
        };

        // Custom Link Renderer
        renderer.link = ({ href, title, text }) => {
            // Security check for href
            let safeHref = href || '#';
            try {
                const url = new URL(safeHref, 'http://localhost'); // Dummy base to parse relative URLs
                if (url.protocol === 'javascript:') {
                    safeHref = '#';
                }
            } catch (e) {
                // If invalid URL, keep as is or sanitize?
            }

            return `<a href="${safeHref}" target="_blank" rel="noopener noreferrer" class="text-[#478cbf] hover:underline" title="${title || ''}">${text}</a>`;
        };

        marked.use({ renderer, breaks: true, gfm: true });
    }

    transform(value: string | null | undefined): SafeHtml {
        if (!value) return '';
        try {
            let html = marked.parse(value) as string;
            // Remove trailing whitespace from HTML
            html = html.trim();
            // Wrap in a div that removes bottom margin from last child
            html = `<div class="markdown-content [&>*:last-child]:!mb-0">${html}</div>`;
            return this.sanitizer.bypassSecurityTrustHtml(html);
        } catch (e) {
            console.error('Error parsing markdown:', e);
            return value || '';
        }
    }
}
