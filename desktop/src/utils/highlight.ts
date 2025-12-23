/**
 * Highlight.js Configuration for Godoty
 * 
 * Using the core version of highlight.js to minimize bundle size,
 * and explicitly registering only the languages we need.
 */

import hljs from 'highlight.js/lib/core'

// Import languages commonly used in Godot development
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import bash from 'highlight.js/lib/languages/bash'
import yaml from 'highlight.js/lib/languages/yaml'
import markdown from 'highlight.js/lib/languages/markdown'
import plaintext from 'highlight.js/lib/languages/plaintext'

// Register languages
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('json', json)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('plaintext', plaintext)
hljs.registerLanguage('text', plaintext)

/**
 * Custom GDScript language definition for highlight.js
 * Based on Godot 4.x GDScript syntax
 */
const gdscript = (hljs: any) => {
  const KEYWORDS = {
    keyword: [
      'and', 'as', 'assert', 'await', 'break', 'breakpoint', 'class', 'class_name',
      'const', 'continue', 'elif', 'else', 'enum', 'export', 'extends', 'for',
      'func', 'if', 'in', 'is', 'match', 'not', 'or', 'pass', 'preload', 'return',
      'self', 'setget', 'signal', 'static', 'super', 'trait', 'var', 'while', 'yield'
    ],
    literal: ['true', 'false', 'null', 'PI', 'TAU', 'INF', 'NAN'],
    built_in: [
      // Common Godot types
      'Vector2', 'Vector2i', 'Vector3', 'Vector3i', 'Vector4', 'Vector4i',
      'Color', 'Rect2', 'Rect2i', 'Transform2D', 'Transform3D',
      'Basis', 'Quaternion', 'AABB', 'Plane', 'Projection',
      'Array', 'Dictionary', 'String', 'StringName', 'NodePath',
      'PackedByteArray', 'PackedInt32Array', 'PackedInt64Array',
      'PackedFloat32Array', 'PackedFloat64Array', 'PackedStringArray',
      'PackedVector2Array', 'PackedVector3Array', 'PackedColorArray',
      'Callable', 'Signal', 'RID',
      // Common nodes
      'Node', 'Node2D', 'Node3D', 'Control', 'CanvasItem',
      'Sprite2D', 'Sprite3D', 'AnimatedSprite2D', 'AnimatedSprite3D',
      'CharacterBody2D', 'CharacterBody3D', 'RigidBody2D', 'RigidBody3D',
      'Area2D', 'Area3D', 'CollisionShape2D', 'CollisionShape3D',
      'Camera2D', 'Camera3D', 'Light2D', 'Light3D',
      'AudioStreamPlayer', 'AudioStreamPlayer2D', 'AudioStreamPlayer3D',
      'Timer', 'Tween', 'AnimationPlayer', 'AnimationTree',
      'Resource', 'Object', 'RefCounted'
    ]
  }

  const ANNOTATION = {
    className: 'meta',
    begin: /@/,
    end: /(?=\s|\(|$)/,
    relevance: 10
  }

  const STRING = {
    className: 'string',
    variants: [
      { begin: '"""', end: '"""' },
      { begin: "'''", end: "'''" },
      { begin: '"', end: '"', illegal: '\\n' },
      { begin: "'", end: "'", illegal: '\\n' },
      { begin: '&"', end: '"' },  // StringName
      { begin: '\\^"', end: '"' }, // NodePath
    ]
  }

  const NUMBER = {
    className: 'number',
    variants: [
      { begin: '\\b0x[0-9a-fA-F_]+' },  // Hex
      { begin: '\\b0b[01_]+' },          // Binary
      { begin: '\\b\\d[\\d_]*\\.?[\\d_]*(?:e[+-]?[\\d_]+)?' }  // Decimal/Float
    ],
    relevance: 0
  }

  const FUNCTION_DEF = {
    className: 'function',
    beginKeywords: 'func',
    end: /:/,
    excludeEnd: true,
    contains: [
      {
        className: 'title.function',
        begin: /[a-zA-Z_]\w*/,
        relevance: 0
      },
      {
        begin: /\(/,
        end: /\)/,
        contains: [
          {
            className: 'params',
            begin: /[a-zA-Z_]\w*/,
            relevance: 0
          },
          {
            className: 'type',
            begin: /:\s*/,
            end: /(?=[,)=])/,
            excludeBegin: true
          }
        ]
      },
      {
        className: 'type',
        begin: /->\s*/,
        end: /:/,
        excludeBegin: true,
        excludeEnd: true
      }
    ]
  }

  const CLASS_DEF = {
    className: 'class',
    beginKeywords: 'class',
    end: /:/,
    excludeEnd: true,
    contains: [
      {
        className: 'title.class',
        begin: /[a-zA-Z_]\w*/,
        relevance: 0
      }
    ]
  }

  return {
    name: 'GDScript',
    aliases: ['gdscript', 'gd'],
    keywords: KEYWORDS,
    contains: [
      hljs.HASH_COMMENT_MODE,
      ANNOTATION,
      STRING,
      NUMBER,
      FUNCTION_DEF,
      CLASS_DEF,
      {
        className: 'variable',
        begin: /\$[a-zA-Z_]\w*/
      }
    ]
  }
}

// Register GDScript
hljs.registerLanguage('gdscript', gdscript)
hljs.registerLanguage('gd', gdscript)

// Export the configured hljs instance
export default hljs

/**
 * Safely highlight code with fallback
 * @param code The code to highlight
 * @param language The language to use for highlighting
 * @returns Highlighted HTML string
 */
export function safeHighlight(code: string, language: string): string {
  // Normalize language name
  const lang = language.toLowerCase().trim()
  
  // Check if language is registered
  const registeredLang = hljs.getLanguage(lang)
  
  if (registeredLang) {
    try {
      return hljs.highlight(code, { language: lang }).value
    } catch {
      // Fall through to auto-detection
    }
  }
  
  // Try auto-detection as fallback
  try {
    const result = hljs.highlightAuto(code)
    return result.value
  } catch {
    // Return escaped plain text as last resort
    return escapeHtml(code)
  }
}

/**
 * Escape HTML entities to prevent XSS
 */
function escapeHtml(text: string): string {
  const htmlEntities: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }
  return text.replace(/[&<>"']/g, char => htmlEntities[char])
}
