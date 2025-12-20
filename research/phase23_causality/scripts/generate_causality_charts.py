
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path

# Setup
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def generate_charts():
    # Load Results
    res_path = DATA_DIR / "lead_lag_results.csv"
    if not res_path.exists():
        print("Results not found")
        return
        
    df = pd.read_csv(res_path)
    
    # Filter for significant/strong links to avoid clutter
    # Threshold > 0.15 correlation for visualization
    strong_links = df[df['Max_Corr'] > 0.15]
    
    # Construct Graph
    G = nx.DiGraph()
    
    for _, row in strong_links.iterrows():
        pair = row['Pair']
        direction = row['Direction']
        corr = row['Max_Corr']
        lag = row['Best_Lag (Min)']
        
        if "->" in direction:
            source, target = direction.split("->")
            G.add_edge(source, target, weight=corr, label=f"{lag}m")
            
    # Plot
    plt.figure(figsize=(10, 8))
    pos = nx.spring_layout(G, k=1.5, seed=42) # k regulates distance
    
    # Nodes
    nx.draw_networkx_nodes(G, pos, node_size=1500, node_color='lightblue', alpha=0.9, edgecolors='black')
    nx.draw_networkx_labels(G, pos, font_size=12, font_weight='bold')
    
    # Edges
    edges = G.edges()
    weights = [G[u][v]['weight'] * 8 for u, v in edges] # Thicker lines
    
    # Draw edges with prominent arrows
    nx.draw_networkx_edges(G, pos, edgelist=edges, width=weights, 
                          edge_color='black', arrows=True, arrowsize=30, 
                          arrowstyle='-|>', connectionstyle="arc3,rad=0.15")
                          
    # Edge Labels (Lag)
    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='red')
    
    plt.title("The Influence Map: Who Leads Whom?\n(Arrow = Direction of Predictive Influence)", fontsize=14)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig(OUT_DIR / "influence_graph.png")
    print(f"Saved {OUT_DIR}/influence_graph.png")

if __name__ == "__main__":
    generate_charts()
