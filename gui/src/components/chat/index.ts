/**
 * index.ts — Barrel exports for the modular Nexus Chat UI components and shared types.
 */

export { default as ChatSidebar } from "./ChatSidebar";
export { default as ChatHeader } from "./ChatHeader";
export { default as ChatMessageItem } from "./ChatMessageItem";
export { default as ChatMessageThread } from "./ChatMessageThread";
export { default as ChatInputBar } from "./ChatInputBar";
export { default as BlackboardDrawer } from "./BlackboardDrawer";

export * from "./types";
export type { ChatSidebarProps } from "./ChatSidebar";
export type { ChatHeaderProps } from "./ChatHeader";
export type { ChatMessageItemProps } from "./ChatMessageItem";
export type { ChatMessageThreadProps } from "./ChatMessageThread";
export type { ChatInputBarProps } from "./ChatInputBar";
export type { BlackboardDrawerProps } from "./BlackboardDrawer";

