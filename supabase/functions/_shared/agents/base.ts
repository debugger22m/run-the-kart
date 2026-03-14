/**
 * BaseAgent — abstract agentic loop for Deno / Supabase Edge Functions.
 *
 * Agentic loop pattern:
 *   1. Send messages to Claude with tool definitions.
 *   2. If Claude responds with tool_use blocks, route them to the right handler.
 *   3. Repeat until Claude returns a plain text response (stop_reason == "end_turn").
 */

import Anthropic from "npm:@anthropic-ai/sdk";

const DEFAULT_MODEL = "claude-sonnet-4-5";

export abstract class BaseAgent {
  protected client: Anthropic;
  protected name: string;
  protected systemPrompt: string;
  protected tools: Anthropic.Tool[];
  protected model: string;
  protected maxTokens: number;
  protected maxIterations: number;

  constructor(options: {
    name: string;
    systemPrompt: string;
    tools: Anthropic.Tool[];
    model?: string;
    maxTokens?: number;
    maxIterations?: number;
  }) {
    this.name = options.name;
    this.systemPrompt = options.systemPrompt;
    this.tools = options.tools;
    this.model = options.model ?? DEFAULT_MODEL;
    this.maxTokens = options.maxTokens ?? 4096;
    this.maxIterations = options.maxIterations ?? 10;

    const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
    if (!apiKey) {
      throw new Error("ANTHROPIC_API_KEY environment variable is not set");
    }
    this.client = new Anthropic({ apiKey });
  }

  /**
   * Must be implemented by subclass — handle tool calls that belong to this agent.
   */
  protected abstract handleOwnToolCall(
    toolName: string,
    input: Record<string, unknown>,
  ): Promise<string>;

  /**
   * Route a tool call to this agent's own handler.
   * Subclasses can override to add skill routing if needed.
   */
  protected async handleToolCall(
    toolName: string,
    input: Record<string, unknown>,
  ): Promise<string> {
    return this.handleOwnToolCall(toolName, input);
  }

  /**
   * Run the agentic loop for a single task.
   * Returns the final text response from Claude once it stops requesting tools.
   */
  async run(userMessage: string): Promise<string> {
    type MessageParam = Anthropic.MessageParam;

    const messages: MessageParam[] = [
      { role: "user", content: userMessage },
    ];

    for (let iteration = 0; iteration < this.maxIterations; iteration++) {
      const hasTools = this.tools.length > 0;

      const params: Anthropic.MessageCreateParamsNonStreaming = {
        model: this.model,
        max_tokens: this.maxTokens,
        system: this.systemPrompt,
        messages,
      };

      if (hasTools) {
        // Cast needed because the SDK type for web_search_20250305 may be typed as a built-in tool
        params.tools = this.tools as Anthropic.Tool[];
        params.tool_choice = { type: "auto", disable_parallel_tool_use: true };
      }

      const response = await this.client.messages.create(params);

      // Serialize assistant content keeping only fields the API accepts on replay
      const assistantContent: Anthropic.ContentBlock[] = [];
      for (const block of response.content) {
        if (block.type === "tool_use") {
          assistantContent.push({
            type: "tool_use",
            id: block.id,
            name: block.name,
            input: block.input,
          } as Anthropic.ToolUseBlock);
        } else if (block.type === "text") {
          assistantContent.push({ type: "text", text: block.text } as Anthropic.TextBlock);
        } else {
          assistantContent.push(block);
        }
      }
      messages.push({ role: "assistant", content: assistantContent });

      if (response.stop_reason === "end_turn") {
        for (const block of response.content) {
          if (block.type === "text") {
            return block.text;
          }
        }
        return "";
      }

      if (response.stop_reason === "tool_use") {
        const toolResults: Anthropic.ToolResultBlockParam[] = [];

        for (const block of response.content) {
          if (block.type !== "tool_use") continue;

          let result: string;
          try {
            result = await this.handleToolCall(
              block.name,
              block.input as Record<string, unknown>,
            );
          } catch (err) {
            // Always return a tool_result for every tool_use block —
            // missing results cause Anthropic to reject the next message.
            result = JSON.stringify({ error: String(err) });
          }

          toolResults.push({
            type: "tool_result",
            tool_use_id: block.id,
            content: result,
          });
        }

        messages.push({ role: "user", content: toolResults });
      }
    }

    console.warn(`[${this.name}] Reached max iterations (${this.maxIterations}).`);
    return "Max iterations reached without a final answer.";
  }
}
