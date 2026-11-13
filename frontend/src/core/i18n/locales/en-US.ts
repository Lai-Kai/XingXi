import {
  CompassIcon,
  GraduationCapIcon,
  ImageIcon,
  MicroscopeIcon,
  PenLineIcon,
  ShapesIcon,
  SparklesIcon,
  VideoIcon,
} from "lucide-react";

import type { Translations } from "./types";

export const enUS: Translations = {
  // Locale meta
  locale: {
    localName: "English",
  },

  // Common
  common: {
    home: "Home",
    settings: "Settings",
    delete: "Delete",
    edit: "Edit",
    rename: "Rename",
    share: "Share",
    openInNewWindow: "Open in new window",
    close: "Close",
    more: "More",
    search: "Search",
    loadMore: "Load more",
    download: "Download",
    thinking: "Thinking",
    artifacts: "Artifacts",
    public: "Public",
    custom: "Custom",
    notAvailableInDemoMode: "Not available in demo mode",
    loading: "Loading...",
    version: "Version",
    lastUpdated: "Last updated",
    code: "Code",
    preview: "Preview",
    cancel: "Cancel",
    save: "Save",
    install: "Install",
    create: "Create",
    import: "Import",
    export: "Export",
    exportAsMarkdown: "Export reading copy",
    exportAsJSON: "Export conversation backup",
    exportSuccess: "Conversation exported",
    regenerate: "Regenerate",
    branch: "Branch conversation",
    showArtifacts: "Show artifacts of this conversation",
  },

  // Home
  home: {
    docs: "Docs",
    blog: "Blog",
  },

  // Welcome
  welcome: {
    greeting: "Xingxi",
    description:
      "A traceable research assistant for Wu culture and Mudu regional history.",

    createYourOwnSkill: "Create your own workflow",
    createYourOwnSkillDescription:
      "Create a custom workflow to help with research, source organization and content preparation.",
  },

  // Clipboard
  clipboard: {
    copyToClipboard: "Copy to clipboard",
    copiedToClipboard: "Copied to clipboard",
    failedToCopyToClipboard: "Failed to copy to clipboard",
    linkCopied: "Link copied to clipboard",
  },

  // Citations
  citations: {
    sourcesSummary: (count) =>
      `Used ${count} ${count === 1 ? "source" : "sources"}`,
    citeCount: (count) => `${count} ${count === 1 ? "cite" : "cites"}`,
    copyReference: (title) => `Copy ${title} reference`,
    copiedReference: (title) => `Copied ${title} reference`,
  },

  // Workspace Changes
  workspaceChanges: {
    title: "Workspace changes",
    editedTitle: (count) => `Edited ${count} ${count === 1 ? "file" : "files"}`,
    badge: (count, additions, deletions) =>
      `${count} ${count === 1 ? "file" : "files"} changed +${additions} -${deletions}`,
    viewChanges: "View changes",
    created: "Created",
    modified: "Modified",
    deleted: "Deleted",
    openFile: "Open file",
    loading: "Loading workspace changes...",
    noChanges: "No workspace changes recorded.",
    diffUnavailable: "Modification details unavailable",
    binaryUnavailable: "Binary file. Modification details unavailable.",
    largeUnavailable: "This file is too large to show modification details.",
    sensitiveUnavailable: "Sensitive path. Content hidden.",
    truncatedUnavailable: "There are too many changes to display.",
    truncatedSummary: "Some changes were truncated.",
  },

  // Input Box
  inputBox: {
    placeholder:
      "Ask about Mudu sites, people, gazetteers, or historical change",
    createSkillPrompt:
      "Help me design a custom research workflow through conversation. Start by asking what task I want to complete.",
    addAttachments: "Add attachments",
    inputPolish: "Polish input",
    inputPolishing: "Polishing input...",
    inputPolishNoChanges: "This input is already clear.",
    inputPolishFailed: "Failed to polish input.",
    inputPolishUndo: "Undo polish",
    inputPolishCancel: "Cancel polishing",
    voiceInputStartLabel: "Dictate with voice",
    voiceInputStopLabel: "Stop voice input",
    voiceInputStart:
      "Dictate with voice. Xingxi receives only transcribed text; audio is handled by your browser or system speech service.",
    voiceInputStop: "Stop voice input",
    voiceInputListening: "Listening... Click to stop voice input.",
    voiceInputUnsupported:
      "Voice input is not supported in this browser. Try Chrome or Edge.",
    voiceInputPermissionDenied:
      "Microphone access was denied. Allow microphone access and try again.",
    voiceInputMicrophoneUnavailable:
      "No microphone was detected. Check your device input and try again.",
    voiceInputUnsupportedLanguage:
      "Voice input does not support the current language in this browser.",
    voiceInputNetworkError:
      "Voice input could not reach the browser speech service.",
    voiceInputNoSpeech: "No speech was detected. Please try again.",
    voiceInputFailed: "Voice input failed. Please try again.",
    mode: "Mode",
    flashMode: "Quick answer",
    flashModeDescription: "Fast and efficient, but may not be accurate",
    reasoningMode: "Reasoning",
    reasoningModeDescription:
      "Reasoning before action, balance between time and accuracy",
    proMode: "In-depth research",
    proModeDescription:
      "Reasoning, planning and executing, get more accurate results, may take more time",
    ultraMode: "Comprehensive research",
    ultraModeDescription:
      "Combine several research directions for complex tasks; may take more time",
    reasoningEffort: "Research depth",
    reasoningEffortMinimal: "Minimal",
    reasoningEffortMinimalDescription: "Find sources and answer directly",
    reasoningEffortLow: "Low",
    reasoningEffortLowDescription:
      "Check key points and prepare a brief answer",
    reasoningEffortMedium: "Medium",
    reasoningEffortMediumDescription: "Compare sources and verify the evidence",
    reasoningEffortHigh: "High",
    reasoningEffortHighDescription:
      "Compare findings in depth and explain uncertainties",
    searchModels: "Search response styles...",
    modelUnavailable:
      "Chat is temporarily unavailable. Please contact an administrator.",
    modelUnavailableShort: "Unavailable",
    surpriseMe: "Surprise",
    surpriseMePrompt: "Surprise me",
    followupLoading: "Generating follow-up questions...",
    followupConfirmTitle: "Send suggestion?",
    followupConfirmDescription:
      "You already have text in the input. Choose how to send it.",
    followupConfirmAppend: "Append & send",
    followupConfirmReplace: "Replace & send",
    suggestionPlaceholderRequired:
      "Replace the suggestion placeholder before sending.",
    goalCommandDescription: "Set, show, or clear an active goal",
    compactCommandDescription:
      "Organize earlier conversation while keeping the full chat visible",
    goalLabel: "Goal",
    goalContinuing: "Continuing {count}/{max}",
    goalContinuationTooltip:
      "Auto-continued {count}/{max} times toward the goal; stops at the limit.",
    goalSet: "Goal set.",
    goalCleared: "Goal cleared.",
    goalNone: "No active goal.",
    goalActive: "Active goal: {goal}",
    goalFailed: "Goal command failed.",
    compactSuccess:
      "Earlier conversation organized. The full chat remains visible and you can continue.",
    compactSkipped: "This conversation does not need organizing yet.",
    compactFailed: "Conversation organization failed. Please try again.",
    suggestions: [
      {
        suggestion: "Write",
        prompt: "Write a blog post about the latest trends on [topic]",
        icon: PenLineIcon,
      },
      {
        suggestion: "Research",
        prompt:
          "Conduct a deep dive research on [topic], and summarize the findings.",
        icon: MicroscopeIcon,
      },
      {
        suggestion: "Collect",
        prompt: "Collect data from [source] and create a report.",
        icon: ShapesIcon,
      },
      {
        suggestion: "Learn",
        prompt: "Learn about [topic] and create a tutorial.",
        icon: GraduationCapIcon,
      },
    ],
    suggestionsCreate: [
      {
        suggestion: "Webpage",
        prompt: "Create a webpage about [topic]",
        icon: CompassIcon,
      },
      {
        suggestion: "Image",
        prompt: "Create an image about [topic]",
        icon: ImageIcon,
      },
      {
        suggestion: "Video",
        prompt: "Create a video about [topic]",
        icon: VideoIcon,
      },
      {
        type: "separator",
      },
      {
        suggestion: "Workflow",
        prompt:
          "Help me design a custom research workflow through conversation. Start by asking what task I want to complete.",
        icon: SparklesIcon,
      },
    ],
    pleaseWaitStreaming: "Please wait for the current response to finish.",
  },

  // Sidebar
  sidebar: {
    newChat: "New chat",
    chats: "Chats",
    channels: "Channels",
    recentChats: "Recent chats",
    demoChats: "Demo chats",
    agents: "Agents",
    scheduledTasks: "Scheduled tasks",
    agentsDisabledTooltip: "Feature not enabled",
  },

  // Scheduled tasks
  scheduledTasks: {
    scheduleType: {
      cron: "Recurring",
      once: "One-time",
    },
    preset: {
      label: "Repeat",
      hourly: "Hourly",
      daily: "Daily",
      weekly: "Weekly",
      monthly: "Monthly",
      custom: "Custom schedule",
    },
    fields: {
      minute: "Minute",
      time: "Time",
      weekday: "On",
      dayOfMonth: "Day of month",
      cron: "Repeat schedule",
      cronPlaceholder: "0 9 * * *",
      runAt: "Run at",
      timezone: "Timezone",
    },
    weekdays: {
      mon: "Mon",
      tue: "Tue",
      wed: "Wed",
      thu: "Thu",
      fri: "Fri",
      sat: "Sat",
      sun: "Sun",
    },
    preview: "Preview",
    cronHelp: "View schedule help",
    create: {
      title: "Create scheduled task",
      taskTitle: "Task title",
      prompt: "Task instructions",
      submit: "Create",
      fillRequired: "Fill all required fields",
    },
    context: {
      fresh: "New conversation",
      reuse: "Continue conversation",
      threadIdPlaceholder: "Conversation number",
    },
    filters: {
      allStatuses: "All statuses",
      enabled: "Enabled",
      paused: "Paused",
      completed: "Completed",
      failed: "Failed",
      allTypes: "All types",
      cron: "Recurring",
      once: "Once",
    },
    detail: {
      contextMode: "Conversation style",
      thread: "Conversation",
      lastThread: "Last conversation",
      schedule: "Schedule",
      nextRun: "Next run",
      lastRun: "Last run",
      lastRunId: "Last execution record",
      lastError: "Last error",
      runsCount: "{count} runs",
      runsCountOne: "{count} run",
      noRuns: "No runs yet",
      noSelection: "No scheduled task selected",
      filteredByThread: "Tasks for the selected conversation",
      loadFailed: "Failed to load scheduled tasks",
    },
    actions: {
      edit: "Edit",
      cancelEdit: "Cancel edit",
      pause: "Pause",
      resume: "Resume",
      trigger: "Trigger now",
      delete: "Delete",
    },
    deleteConfirm:
      "Are you sure you want to delete this scheduled task? This action cannot be undone.",
    errors: {
      create: "Failed to create scheduled task",
      update: "Failed to update scheduled task",
      pause: "Failed to pause scheduled task",
      resume: "Failed to resume scheduled task",
      trigger: "Failed to trigger scheduled task",
      delete: "Failed to delete scheduled task",
    },
    edit: {
      titlePlaceholder: "Edit title",
      promptPlaceholder: "Edit prompt",
      submit: "Save edit",
    },
    status: {
      enabled: "Enabled",
      paused: "Paused",
      running: "Running",
      completed: "Completed",
      failed: "Failed",
      cancelled: "Cancelled",
    },
    runTrigger: { scheduled: "scheduled", manual: "manual" },
    runStatus: {
      queued: "Queued",
      running: "Running",
      success: "Success",
      failed: "Failed",
      skipped: "Skipped",
      interrupted: "Interrupted",
    },
    recipes: {
      label: "Quick create",
      mapSources: {
        title: "Daily map source notes",
        desc: "Review Mudu map sources and citations daily at 09:00",
        prompt:
          "Review gazetteers, inscriptions and archives you are authorized to access for the Mudu historical map. Summarize source leads about place names, waterways, bridges, historic buildings, people and events. Include excerpts, document titles, volume/page locators and available evidence IDs. Separate existing records from unverified leads; do not describe material as new without a verified update date. Produce a reading report only; do not modify or publish map data.",
      },
      mapPoints: {
        title: "Map point evidence review",
        desc: "Check citations, dates and open questions daily at 09:00",
        prompt:
          "Search authorized sources for Mudu historical map point research. If the map point list or review states cannot be accessed, say so explicitly; do not present source candidates as existing map points. For records you can verify, List pending, disputed, undated and uncertain-location records, their existing evidence, missing information and next verification steps. Include document titles, volume/page locators and available evidence IDs. Distinguish exact coordinates from inferred areas; mark unknown locations explicitly and never invent or derive coordinates. Produce a review checklist only; do not modify points, review status or published data.",
      },
      placeNames: {
        title: "Historical place-name review",
        desc: "Review aliases and period-specific evidence daily at 09:00",
        prompt:
          "Review historical aliases, dynasties and present-day correspondences for place names in Mudu and its surrounding map. Use only authorized sources, listing candidate names, historical context, document titles, volume/page locators and available evidence IDs. Do not merge names from different contexts. Retain every candidate and mark uncertainty when evidence is ambiguous or insufficient. Produce a comparison and verification report only; do not merge entities, rename map points or publish knowledge.",
      },
      mapWeekly: {
        title: "Weekly historical map brief",
        desc: "Summarize map research every Monday at 09:00",
        prompt:
          "Prepare a weekly Mudu historical map research brief from authorized map points, dated events, relationships and source material. Classify an item as a change this week only when its update date can be verified; otherwise label it material reviewed this time. Summarize findings, citations, disputes and missing information, then identify three verification priorities for next week. Include real document titles, volume/page locators and available evidence IDs. Do not invent change counts, coordinates or historical conclusions. Produce a brief only; do not modify or publish map data.",
      },
    },
  },

  // Agents
  agents: {
    title: "Agents",
    description:
      "Create and manage custom agents with specialized prompts and capabilities.",
    newAgent: "New Agent",
    emptyTitle: "No custom agents yet",
    emptyDescription:
      "Create your first custom agent with a specialized system prompt.",
    featureDisabledTitle: "Agents feature is not enabled",
    featureDisabledDescription:
      "This feature is not enabled on this server. Please contact your administrator.",
    chat: "Chat",
    delete: "Delete",
    deleteConfirm:
      "Are you sure you want to delete this agent? This action cannot be undone.",
    deleteSuccess: "Agent deleted",
    newChat: "New chat",
    createPageTitle: "Design your Agent",
    createPageSubtitle:
      "Describe the agent you want — I'll help you create it through conversation.",
    nameStepTitle: "Name your new Agent",
    nameStepHint:
      "Letters, digits, and hyphens only — stored lowercase (e.g. code-reviewer)",
    nameStepPlaceholder: "e.g. code-reviewer",
    nameStepContinue: "Continue",
    nameStepInvalidError:
      "Invalid name — use only letters, digits, and hyphens",
    nameStepAlreadyExistsError: "An agent with this name already exists",
    nameStepNetworkError:
      "Connection failed. Please check your network and try again.",
    nameStepCheckError: "Could not verify name availability — please try again",
    nameStepCheckErrorWithDetail: "Name check failed: {detail}",
    nameStepApiDisabledError:
      "Custom assistant management is not enabled. Please contact your administrator.",
    nameStepBootstrapMessage:
      "The new assistant is called {name}. Help me design its purpose, work style and instructions before saving it.",
    save: "Save agent",
    saving: "Saving agent...",
    saveRequested:
      "Save requested. Xingxi is generating and saving an initial version now.",
    saveHint:
      "You can save this agent at any time from the top-right menu, even if this is only a first draft.",
    saveCommandMessage:
      "Please save this custom assistant using what we have discussed. Fill in any small missing details reasonably and save without asking for confirmation again.",
    agentCreatedPendingRefresh:
      "The agent was created, but Xingxi could not load it yet. Please refresh this page in a moment.",
    more: "More actions",
    agentCreated: "Agent created!",
    startChatting: "Start chatting",
    backToGallery: "Back to Gallery",
  },

  // Breadcrumb
  breadcrumb: {
    workspace: "Workspace",
    chats: "Chats",
  },

  // Workspace
  workspace: {
    officialWebsite: "Xingxi's official website",
    githubTooltip: "Xingxi on GitHub",
    settingsAndMore: "Settings and more",
    visitGithub: "Xingxi on GitHub",
    reportIssue: "Report an issue",
    contactUs: "Contact us",
    about: "About Xingxi",
    logout: "Log out",
    gatewayUnavailable: "Gateway is temporarily unavailable.",
    gatewayUnavailableRetrying: "Retrying in the background…",
  },

  // Conversation
  conversation: {
    noMessages: "No messages yet",
    startConversation: "Start a conversation to see messages here",
    branchCreated: "Conversation branch created",
    branchFailed: "Failed to branch conversation.",
  },

  // Chats
  chats: {
    searchChats: "Search chats",
    loadMoreToSearch: "Load more to search older conversations",
    loadingMore: "Loading more...",
    loadOlderChats: "Load older chats",
  },

  // Sidecar
  sidecar: {
    title: "Side chat",
    open: "Open side chat",
    close: "Close side chat",
    delete: "Delete side chat",
    deleteConfirm:
      "Are you sure you want to delete this side chat? This action cannot be undone. To simply hide it, use the side chat toggle in the header instead.",
    deleteSuccess: "Side chat deleted",
    deleteFailed: "Failed to delete side chat.",
    addToConversation: "Add to conversation",
    askInSideChat: "Ask in side chat",
    reference: "Reference",
    selectedTextFragment: "{count} selected text fragment",
    selectedTextFragments: "{count} selected text fragments",
    clearReferences: "Clear selected references",
    emptyTitle: "Ask a follow-up",
    emptyDescription: "Ask a follow-up grounded in the referenced text.",
    placeholder: "Ask a deeper follow-up...",
    send: "Send",
    sendFailed: "Failed to send side chat message.",
    noContext: "No related content selected",
    continuing: "Continue in this side chat",
    selectionCrossesMessages:
      "Selection spans multiple messages. Select text within a single reply to quote it.",
  },

  // Channels
  channels: {
    title: "Channels",
    connect: "Connect",
    modify: "Modify",
    reconnect: "Reconnect",
    disconnect: "Disconnect",
    connected: "Connected",
    notConnected: "Not connected",
    pending: "Pending",
    revoked: "Disconnected",
    disabled: "Disabled",
    unconfigured: "Not configured",
    unavailable: "Channel connections are unavailable right now.",
    unavailableShort: "Unavailable",
    setupTitle: (name: string) => `Connect ${name}`,
    setupEditTitle: (name: string) => `Modify ${name}`,
    bindingInstruction: (name: string, code: string) =>
      `Send /connect ${code} to the Xingxi ${name} bot to connect your account.`,
    setupDescription:
      "Enter the connection details provided by your administrator.",
    saveAndConnect: "Save and connect",
    saveChanges: "Save changes",
    descriptions: {
      telegram: "Telegram direct messages through your Xingxi bot.",
      slack: "Slack workspace messages and mentions.",
      discord: "Discord server messages through your Xingxi bot.",
      feishu: "Feishu and Lark messages through your Xingxi app.",
      dingtalk: "DingTalk Stream Push messages through your Xingxi bot.",
      wechat: "WeChat iLink messages through your Xingxi bot.",
      wecom: "WeCom messages through your Xingxi AI bot.",
    },
    connectedAs: (name: string) => `Connected as ${name}.`,
  },

  // Page titles (document title)
  pages: {
    appName: "Xingxi",
    chats: "Chats",
    newChat: "New chat",
    untitled: "Untitled",
  },

  // Tool calls
  toolCalls: {
    moreSteps: (count: number) => `${count} more step${count === 1 ? "" : "s"}`,
    lessSteps: "Less steps",
    executeCommand: "Execute command",
    presentFiles: "Present files",
    needYourHelp: "Need your help",
    useTool: (_toolName: string) => "Preparing research",
    searchFor: (query: string) => `Search for "${query}"`,
    searchForRelatedInfo: "Search for related information",
    searchForRelatedImages: "Search for related images",
    searchForRelatedImagesFor: (query: string) =>
      `Search for related images for "${query}"`,
    searchOnWebFor: (query: string) => `Search on the web for "${query}"`,
    viewWebPage: "View web page",
    listFolder: "List folder",
    readFile: "Read file",
    writeFile: "Write file",
    clickToViewContent: "Click to view file content",
    writeTodos: "Update to-do list",
    skillInstallTooltip: "Add a research capability to Xingxi",
  },

  researchTrace: {
    title: "Research process",
    running: "Preparing research…",
    complete: "Complete",
    consolidating: "Verify evidence and organize the conclusion",
    phases: {
      planning: "Break down the research question",
      sources: "Search documentary evidence",
      graph: "Query people, places, and event relationships",
      timeline: "Build the historical timeline",
      map: "Verify map locations",
      gloss: "Interpret the classical text",
      names: "Verify historical names and aliases",
      comparison: "Cross-check historical sources",
      image: "Inspect the uploaded image",
    },
  },

  humanInput: {
    answered: "Answered",
    pending: "Sending...",
    readOnly: "Read only",
    otherLabel: "Other answer",
    otherPlaceholder: "Type another answer...",
    submit: "Submit",
    emptyError: "Enter an answer before submitting.",
    answeredValue: (value: string) => `Answered: ${value}`,
  },

  // Subtasks
  uploads: {
    uploading: "Uploading...",
    uploadingFiles: "Uploading files, please wait...",
    uploadFailed: "Unable to upload the attachment. Please try again.",
    limitsHint: (maxFiles: number, maxFileSize: string, maxTotalSize: string) =>
      `Add attachments (up to ${maxFiles} files, ${maxFileSize} each, ${maxTotalSize} total). Most regular file types are supported; compress macOS .app bundles first.`,
    filesTooLarge: (files: string, maxFileSize: string) =>
      `Files exceeding the ${maxFileSize} per-file limit were not added: ${files}.`,
    tooManyFiles: (count: number, maxFiles: number) =>
      `${count} file${count === 1 ? " was" : "s were"} not added. You can attach up to ${maxFiles} files at once.`,
    totalSizeTooLarge: (count: number, maxTotalSize: string) =>
      `${count} file${count === 1 ? " was" : "s were"} not added. Attachments can total up to ${maxTotalSize}.`,
  },

  subtasks: {
    subtask: "Subtask",
    executing: (count: number) =>
      `Executing ${count === 1 ? "" : count + " "}subtask${count === 1 ? "" : "s in parallel"}`,
    in_progress: "Running subtask",
    completed: "Subtask completed",
    failed: "Subtask failed",
  },

  // Usage statistics
  tokenUsage: {
    title: "Usage statistics",
    label: "Usage",
    input: "Input",
    output: "Output",
    total: "Total",
    view: "Display",
    unavailable: "No usage statistics available.",
    unavailableShort: "No usage returned",
    collecting: "Collecting usage",
    note: "Usage statistics are for reference.",
    presets: {
      off: "Off",
      summary: "Summary",
      perTurn: "Per turn",
      debug: "Details",
    },
    presetDescriptions: {
      off: "Hide usage statistics.",
      summary: "Show only the current conversation total in the header.",
      perTurn: "Show usage statistics for each reply.",
      debug: "Show usage statistics for each step.",
    },
    finalAnswer: "Final answer",
    stepTotal: "Step total",
    sharedAttribution: "Shared across multiple actions in this step",
    subagent: (description: string) => `Task: ${description}`,
    startTodo: (content: string) => `Start To-do: ${content}`,
    completeTodo: (content: string) => `Complete To-do: ${content}`,
    updateTodo: (content: string) => `Update To-do: ${content}`,
    removeTodo: (content: string) => `Remove To-do: ${content}`,
  },

  // Shortcuts
  shortcuts: {
    searchActions: "Search actions...",
    noResults: "No results found.",
    actions: "Actions",
    keyboardShortcuts: "Keyboard Shortcuts",
    keyboardShortcutsDescription:
      "Navigate Xingxi faster with keyboard shortcuts.",
    openCommandPalette: "Open Command Palette",
    toggleSidebar: "Toggle Sidebar",
  },

  // Settings
  settings: {
    title: "Settings",
    description: "Adjust how Xingxi looks and behaves for you.",
    sections: {
      account: "Account",
      appearance: "Appearance",
      channels: "Channels",
      memory: "Memory",
      tools: "Helpful features",
      skills: "Research capabilities",
      notification: "Notification",
      about: "About",
    },
    memory: {
      title: "Memory",
      loadError: "Memory could not be loaded. Please try again later.",
      actionError:
        "The memory operation could not be completed. Please try again later.",
      description:
        "Xingxi automatically learns from your conversations in the background. These memories help Xingxi understand you better and deliver a more personalized experience.",
      empty: "No memory data to display.",
      accountDisabledTitle:
        "Long-term memory is disabled for this test account",
      accountDisabledDescription:
        "Conversations on this account do not use long-term memory, allowing independent research without earlier preferences.",
      globallyDisabledDescription:
        "Long-term memory is currently disabled for the whole system. Conversations do not read or write cross-session memory.",
      rawJson: "Memory backup",
      exportButton: "Export memory",
      exportSuccess: "Memory exported",
      importButton: "Import memory",
      importConfirmTitle: "Import memory?",
      importConfirmDescription:
        "This will overwrite your current memory with the selected backup.",
      importFileLabel: "Selected file",
      importInvalidFile:
        "The memory file could not be read. Please choose a previously exported memory backup.",
      importSuccess: "Memory imported",
      manualFactSource: "Manual",
      addFact: "Add fact",
      addFactTitle: "Add memory fact",
      editFactTitle: "Edit memory fact",
      addFactSuccess: "Fact created",
      editFactSuccess: "Fact updated",
      clearAll: "Clear all memory",
      clearAllConfirmTitle: "Clear all memory?",
      clearAllConfirmDescription:
        "This will remove all saved summaries and facts. This action cannot be undone.",
      clearAllSuccess: "All memory cleared",
      factDeleteConfirmTitle: "Delete this fact?",
      factDeleteConfirmDescription:
        "This fact will be removed from memory immediately. This action cannot be undone.",
      factDeleteSuccess: "Fact deleted",
      factContentLabel: "Content",
      factCategoryLabel: "Category",
      factConfidenceLabel: "Certainty",
      factContentPlaceholder: "Describe the memory fact you want to save",
      factCategoryPlaceholder: "For example: background or research preference",
      factConfidenceHint: "Choose how certain you are about this memory.",
      factSave: "Save fact",
      factValidationContent: "Fact content cannot be empty.",
      factValidationConfidence: "Please choose a valid certainty level.",
      noFacts: "No saved facts yet.",
      summaryReadOnly:
        "Summary sections are read-only for now. You can currently add, edit, or delete individual facts, or clear all memory.",
      memoryFullyEmpty: "No memory saved yet.",
      factPreviewLabel: "Fact to delete",
      searchPlaceholder: "Search memory",
      filterAll: "All",
      filterFacts: "Facts",
      filterSummaries: "Summaries",
      noMatches: "No matching memory found.",
      markdown: {
        overview: "Overview",
        userContext: "Personal background",
        work: "Work",
        personal: "Personal",
        topOfMind: "Top of mind",
        historyBackground: "History",
        recentMonths: "Recent months",
        earlierContext: "Earlier background",
        longTermBackground: "Long-term background",
        updatedAt: "Updated at",
        facts: "Facts",
        empty: "(empty)",
        table: {
          category: "Category",
          confidence: "Certainty",
          confidenceLevel: {
            veryHigh: "Very high",
            high: "High",
            normal: "Normal",
            unknown: "Unknown",
          },
          content: "Content",
          source: "Source",
          createdAt: "CreatedAt",
          view: "View",
        },
      },
    },
    appearance: {
      themeTitle: "Theme",
      themeDescription:
        "Choose how the interface follows your device or stays fixed.",
      system: "System",
      light: "Light",
      dark: "Dark",
      systemDescription: "Match the operating system preference automatically.",
      lightDescription: "Bright palette with higher contrast for daytime.",
      darkDescription: "Dim palette that reduces glare for focus.",
      languageTitle: "Language",
      languageDescription: "Switch between languages.",
    },
    tools: {
      title: "Helpful features",
      loadError:
        "Additional features could not be loaded. Please try again later.",
      description:
        "Enable helpful features for finding sources, managing files and related tasks.",
      adminRequired:
        "Administrator access is required to manage these features.",
      empty: "No additional features available.",
    },
    channels: {
      title: "Channels",
      description:
        "Connect IM accounts that can send messages to Xingxi from outside the browser.",
      disabled:
        "Message connections are not enabled. Please contact an administrator.",
    },
    skills: {
      retryLoad: "Reload",
      title: "Research capabilities",
      loadError:
        "Research capabilities could not be loaded. Please try again later.",
      description: "Manage built-in and custom workflows for your research.",
      createSkill: "Create workflow",
      emptyTitle: "No research capabilities yet",
      emptyDescription:
        "Create a custom research workflow or ask an administrator to add capabilities for your task.",
      emptyButton: "Create your first workflow",
      adminRequired:
        "Administrator access is required to manage research capabilities.",
      installAdminRequired:
        "Administrator access is required to add research capabilities.",
      installSuccess: "Research capability added.",
      installFailed: "Unable to add the research capability. Please try again.",
    },
    notification: {
      title: "Notification",
      description:
        "Xingxi only sends a completion notification when the window is not active. This is especially useful for long-running tasks so you can switch to other work and get notified when done.",
      requestPermission: "Request notification permission",
      deniedHint:
        "Notification permission was denied. You can enable it in your browser's site settings to receive completion alerts.",
      testButton: "Send test notification",
      testTitle: "Xingxi",
      testBody: "This is a test notification.",
      notSupported: "Your browser does not support notifications.",
      disableNotification: "Disable notification",
    },
    account: {
      profileTitle: "Profile",
      email: "Email",
      role: "Role",
      ssoProvider: "Sign-in method",
      changePasswordTitle: "Change Password",
      changePasswordDescription: "Update your account password.",
      ssoPasswordDescription:
        "Your password is managed by your sign-in account.",
      ssoPasswordMessage:
        "This account uses unified sign-in. Please change its password with the account provider.",
      currentPassword: "Current password",
      newPassword: "New password",
      confirmNewPassword: "Confirm new password",
      passwordMismatch: "New passwords do not match",
      passwordTooShort: "Password must be at least 8 characters",
      passwordChangedSuccess: "Password changed successfully",
      passwordChangeError:
        "The password could not be changed. Please check your current password and try again.",
      networkError: "Network error. Please try again.",
      updating: "Updating...",
      updatePassword: "Update Password",
      signOut: "Sign Out",
    },
    acknowledge: {
      emptyTitle: "Acknowledgements",
      emptyDescription: "Credits and acknowledgements will show here.",
    },
  },
  login: {
    signInTitle: "Sign in to your account",
    createAccountTitle: "Create a new account",
    email: "Email",
    emailPlaceholder: "you@example.com",
    password: "Password",
    passwordPlaceholder: "•••••••",
    pleaseWait: "Please wait...",
    signIn: "Sign In",
    createAccount: "Create Account",
    createAdminAccount: "Create admin account",
    adminSetupRequiredTitle: "Administrator setup is required",
    adminSetupRequiredDescription:
      "Xingxi needs an administrator account before new regular accounts can be created.",
    orContinueWith: "Or continue with",
    ssoHint:
      "If your account uses single sign-on, sign in with the option below instead.",
    continueWith: (provider: string) => `Continue with ${provider}`,
    noAccountSignUp: "Don't have an account? Sign up",
    haveAccountSignIn: "Already have an account? Sign in",
    backToHome: "← Back to home",
    networkError: "Network error. Please try again.",
    authFailed: "Authentication failed.",
    errors: {
      sso_failed:
        "Unified sign-in failed. Please try again or use email login.",
      sso_cancelled: "Unified sign-in was cancelled.",
      sso_account_exists:
        "An account with this email already exists. Please sign in with your password or contact your administrator.",
      sso_not_allowed:
        "Unified sign-in is not available for your account. Contact your administrator.",
    },
  },
};
