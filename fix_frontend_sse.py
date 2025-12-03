#!/usr/bin/env python3
"""
Script to fix frontend SSE streaming display issue
"""

# Read the current file
with open("C:/Users/eugen/Documents/Github/Godoty/frontend/src/app/app.component.ts", "r") as f:
    content = f.read()

# Fix 1: Update imports
content = content.replace(
    "import { Component, signal, computed, effect, ViewChild, ElementRef, AfterViewChecked, OnInit } from '@angular/core';",
    "import { Component, signal, computed, effect, ViewChild, ElementRef, AfterViewChecked, OnInit, ChangeDetectorRef, NgZone } from '@angular/core';"
)

# Fix 2: Update constructor
old_constructor = '''  constructor(
    private chatService: ChatService,
    private desktopService: DesktopService
  ) { }'''

new_constructor = '''  constructor(
    private chatService: ChatService,
    private desktopService: DesktopService,
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone
  ) { }'''

content = content.replace(old_constructor, new_constructor)

# Fix 3: Add signal monitoring in constructor
old_constructor_body = '''  constructor(
    private chatService: ChatService,
    private desktopService: DesktopService,
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone
  ) { }'''

new_constructor_body = '''  constructor(
    private chatService: ChatService,
    private desktopService: DesktopService,
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone
  ) {
    // Monitor signal changes for debugging
    effect(() => {
      const messages = this.messages();
      console.log('[AppComponent] Signal updated - messages count:', messages.length);
      const lastMsg = messages[messages.length - 1];
      if (lastMsg) {
        console.log('[AppComponent] Last message content length:', lastMsg.content.length);
        console.log('[AppComponent] Last message events count:', lastMsg.events?.length || 0);
      }
    });
  }'''

content = content.replace(new_constructor, new_constructor_body)

# Write the updated content back
with open("C:/Users/eugen/Documents/Github/Godoty/frontend/src/app/app.component.ts", "w") as f:
    f.write(content)

print("Updated frontend imports and constructor for SSE fix")