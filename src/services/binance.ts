/**
 * Represents a trading pair on Binance.
 */
export interface TradingPair {
  /**
   * The symbol of the trading pair (e.g., BTCUSDT).
   */
  symbol: string;

  /**
   * The current price of the trading pair.
   */
  currentPrice: number;

  /**
   * The volume of the trading pair in the last 24 hours.
   */
  volume24h: number;

  /**
   * The change in price in the last 24 hours.
   */
  priceChange24h: number;
}

/**
 * Asynchronously retrieves the ticker price for a given symbol from Binance API.
 *
 * @param symbol The trading symbol to fetch the price for (e.g., 'BTCUSDT').
 * @returns A promise that resolves to the current price of the symbol.
 */
export async function getTickerPrice(symbol: string): Promise<number> {
  // TODO: Implement this by calling the Binance API.

  return 30000;
}

/**
 * Asynchronously retrieves the top performing trading pairs from Binance API.
 *
 * @returns A promise that resolves to an array of TradingPair objects.
 */
export async function getTopPerformingPairs(): Promise<TradingPair[]> {
  // TODO: Implement this by calling the Binance API.

  return [
    {
      symbol: 'BTCUSDT',
      currentPrice: 30000,
      volume24h: 10000,
      priceChange24h: 1.5,
    },
    {
      symbol: 'ETHUSDT',
      currentPrice: 2000,
      volume24h: 5000,
      priceChange24h: 2.0,
    },
  ];
}

