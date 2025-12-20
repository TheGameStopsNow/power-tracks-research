#!/usr/bin/env python3
"""
Options Overlay: The Control Grid
=================================
Phase 29: System Cartography

Objectives:
1. Map the "Gravity Wells" (Strike Prices).
2. Calculate "Pinning Strength" (Price adherence to the Grid).
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional

class OptionsOverlay:
    def __init__(self, price_data: pd.DataFrame, options_flow: pd.DataFrame):
        """
        :param price_data: DataFrame with index=Timestamp, columns=['close', etc.]
        :param options_flow: DataFrame with ['strike_price', 'size', 'date']
        """
        self.prices = price_data
        self.flow = options_flow
        
    def identify_magnets(self, top_n: int = 5) -> List[float]:
        """
        Identify 'Magnet Strikes' based on total volume/size in the flow data.
        """
        if self.flow.empty:
            return []
        
        # Simple aggregation: Total Volume per Strike
        # In a full system, we'd filter by Expiry and Call/Put GEX.
        magnets = self.flow.groupby("strike_price")["size"].sum().sort_values(ascending=False).head(top_n)
        return magnets.index.tolist()

    def calculate_gravity_score(self, magnet_strikes: List[float]) -> Dict:
        """
        Calculate how effectively the Magnet Strikes are 'pulling' the price.
        High Score = Price stays very close to magnets.
        """
        if not magnet_strikes:
            return {"score": 0.0, "mean_dist_pct": 0.0}
            
        close_prices = self.prices["close"].values
        distances = []
        
        for p in close_prices:
            # Find distance to NEAREST magnet
            d = min([abs(p - k) for k in magnet_strikes])
            distances.append(d)
            
        mean_dist = np.mean(distances)
        avg_price = np.mean(close_prices)
        
        # Normalize
        pct_dist = mean_dist / avg_price if avg_price > 0 else 1.0
        
        # Score = Inverse of distance. 
        # If mean distance is 0.5%, score is 200. If 1%, score 100.
        score = 1.0 / (pct_dist * 100) if pct_dist > 0 else 0.0
        
        return {
            "magnets": magnet_strikes,
            "mean_dist_raw": mean_dist,
            "mean_dist_pct": pct_dist,
            "gravity_score": score
        }

    def check_grid_alignment(self, tolerance_pct: float = 0.01) -> float:
        """
        Percentage of time price is within 'tolerance' of a Magnet.
        """
        magnets = self.identify_magnets()
        if not magnets:
            return 0.0
            
        hits = 0
        total = len(self.prices)
        
        for p in self.prices["close"].values:
            is_aligned = any(abs(p - k)/p < tolerance_pct for k in magnets)
            if is_aligned:
                hits += 1
                
        return hits / total

def run_overlay_test():
    print("Testing Options Overlay...")
    
    # Mock Data for standalone test
    dates = pd.date_range("2024-01-01", periods=100, freq="h")
    prices = pd.DataFrame({
        "close": [10.0, 10.05, 10.10, 9.95, 10.00, 15.0, 14.9, 15.1, 15.0] * 11 + [10.0]
    }, index=dates) # Lots of time near 10 and 15
    
    flow = pd.DataFrame({
        "strike_price": [10.0, 15.0, 20.0],
        "size": [1000, 500, 100]
    })
    
    overlay = OptionsOverlay(prices, flow)
    magnets = overlay.identify_magnets(top_n=2)
    print(f"Magnets Identified: {magnets}")
    
    stats = overlay.calculate_gravity_score(magnets)
    print(f"Gravity Score: {stats['gravity_score']:.2f}")
    
    alignment = overlay.check_grid_alignment(tolerance_pct=0.01)
    print(f"Grid Alignment: {alignment:.1%} of bars are on the grid.")

if __name__ == "__main__":
    run_overlay_test()
