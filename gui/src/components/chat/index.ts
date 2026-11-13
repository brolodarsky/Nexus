/**
 * index.ts — Barrel exports for the modular Nexus Chat UI components and shared types.
 */

export { default as ChatSidebar } from "./ChatSidebar";
export { default as ChatHeader } from "./ChatHeader";
export { default as BranchLineageBar } from "./BranchLineageBar";
export { default as MessageBranchTrigger } from "./MessageBranchTrigger";
export { default as ChatMessageItem } from "./ChatMessageItem";
export { default as ChatMessageThread } from "./ChatMessageThread";
export { default as ChatInputBar } from "./ChatInputBar";
export { useChatBranching } from "./useChatBranching";

export * from "./types";
export type { ChatSidebarProps } from "./ChatSidebar";
export type { ChatHeaderProps } from "./ChatHeader";
export type { BranchLineageBarProps } from "./BranchLineageBar";
export type { MessageBranchTriggerProps } from "./MessageBranchTrigger";
export type { ChatMessageItemProps } from "./ChatMessageItem";
export type { ChatMessageThreadProps } from "./ChatMessageThread";
export type { ChatInputBarProps } from "./ChatInputBar";

