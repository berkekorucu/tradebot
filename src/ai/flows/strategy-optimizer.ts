// @ts-nocheck
'use server';

/**
 * @fileOverview AI-powered strategy optimizer flow.
 *
 * - optimizeTradingStrategy - A function that suggests optimized trading strategies based on historical data.
 * - OptimizeTradingStrategyInput - The input type for the optimizeTradingStrategy function.
 * - OptimizeTradingStrategyOutput - The return type for the optimizeTradingStrategy function.
 */

import {ai} from '@/ai/ai-instance';
import {z} from 'genkit';

const OptimizeTradingStrategyInputSchema = z.object({
  historicalData: z.string().describe('Historical trading data in CSV format.'),
  currentStrategy: z.string().optional().describe('The current trading strategy being used (optional).'),
  optimizationGoals: z
    .string()
    .describe(
      'Specific goals for optimization, such as maximizing profit, minimizing risk, or increasing trade frequency.'
    ),
});
export type OptimizeTradingStrategyInput = z.infer<typeof OptimizeTradingStrategyInputSchema>;

const OptimizeTradingStrategyOutputSchema = z.object({
  suggestedStrategy: z
    .string()
    .describe(
      'A detailed description of the suggested optimized trading strategy, including specific parameters and rules.'
    ),
  rationale: z
    .string()
    .describe(
      'Explanation of why the suggested strategy is expected to perform better, based on the analysis of historical data and optimization goals.'
    ),
  riskAssessment: z.string().describe('Assessment of the risks associated with the suggested strategy.'),
});
export type OptimizeTradingStrategyOutput = z.infer<typeof OptimizeTradingStrategyOutputSchema>;

export async function optimizeTradingStrategy(
  input: OptimizeTradingStrategyInput
): Promise<OptimizeTradingStrategyOutput> {
  return optimizeTradingStrategyFlow(input);
}

const prompt = ai.definePrompt({
  name: 'optimizeTradingStrategyPrompt',
  input: {
    schema: z.object({
      historicalData: z.string().describe('Historical trading data in CSV format.'),
      currentStrategy: z.string().optional().describe('The current trading strategy being used (optional).'),
      optimizationGoals: z
        .string()
        .describe(
          'Specific goals for optimization, such as maximizing profit, minimizing risk, or increasing trade frequency.'
        ),
    }),
  },
  output: {
    schema: z.object({
      suggestedStrategy: z
        .string()
        .describe(
          'A detailed description of the suggested optimized trading strategy, including specific parameters and rules.'
        ),
      rationale: z
        .string()
        .describe(
          'Explanation of why the suggested strategy is expected to perform better, based on the analysis of historical data and optimization goals.'
        ),
      riskAssessment: z.string().describe('Assessment of the risks associated with the suggested strategy.'),
    }),
  },
  prompt: `You are an AI-powered trading strategy optimizer. Analyze the provided historical trading data and suggest an optimized trading strategy based on the user's goals.

Historical Data: {{{historicalData}}}

Current Strategy (if any): {{{currentStrategy}}}

Optimization Goals: {{{optimizationGoals}}}

Based on your analysis, provide a detailed description of the suggested strategy, explain why it is expected to perform better, and assess the associated risks.`,
});

const optimizeTradingStrategyFlow = ai.defineFlow<
  typeof OptimizeTradingStrategyInputSchema,
  typeof OptimizeTradingStrategyOutputSchema
>(
  {
    name: 'optimizeTradingStrategyFlow',
    inputSchema: OptimizeTradingStrategyInputSchema,
    outputSchema: OptimizeTradingStrategyOutputSchema,
  },
  async input => {
    const {output} = await prompt(input);
    return output!;
  }
);
