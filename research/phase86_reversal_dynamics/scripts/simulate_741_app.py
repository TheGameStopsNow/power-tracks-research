import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import concurrent.futures
import time


# --- Configuration ---
st.set_page_config(page_title="741 Simulation", layout="wide")

# Set non-interactive backend to prevent hanging on some systems
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

st.title("741 Simulation Interactive App")
st.markdown("""
This app simulates a stock price path using a custom autoregressive model with specific lag coefficients.
""")

# --- Sidebar Inputs ---
st.sidebar.header("Simulation Parameters")

# Global Target Symbol
target_symbol = st.sidebar.text_input("Target Symbol (e.g. GME, BTC-USD)", value="GME", key="target_symbol_input").strip().upper()

if st.sidebar.button("Sync Params to Ticker"):
    try:
        import yfinance as yf
        # Fetch full history to find start
        with st.spinner(f"Fetching metadata for {target_symbol}..."):
            history = yf.download(target_symbol, period="max", progress=False)
        
        if not history.empty:
            # Determine start parameters
            first_date = history.index[0]
            # Handle multi-level column if necessary
            if isinstance(history.columns, pd.MultiIndex):
                # Try simple access or iloc
                try:
                    first_close = history['Close'][target_symbol].iloc[0]
                except:
                    first_close = history['Close'].iloc[0, 0]
            else:
                first_close = history['Close'].iloc[0]
                
            now = pd.Timestamp.now()
            duration_years = (now - first_date).days / 365.25
            

            # Update Session State for Widgets
            # distinct keys are required for the widgets to update
            st.session_state['sim_start_date_widget'] = first_date.date()
            st.session_state['sim_years_widget'] = int(max(1, round(duration_years)))
            st.session_state['sim_start_price_widget'] = float(first_close)
            
            # Also update the backing storage if used
            st.session_state['sim_start_date'] = first_date.date()
            st.session_state['sim_years'] = int(max(1, round(duration_years)))
            st.session_state['sim_start_price'] = float(first_close)
            
            st.success(f"Synced to {target_symbol}: {first_date.date()}, ${first_close:.2f}, {int(duration_years)}y")
            st.rerun()
        else:
            st.error(f"No data found for {target_symbol}")
    except Exception as e:
        st.error(f"Sync failed: {e}")

# Initialize session state for widgets if not present
if 'sim_start_date' not in st.session_state:
    st.session_state['sim_start_date'] = pd.to_datetime("2002-02-13").date()
if 'sim_years' not in st.session_state:
    st.session_state['sim_years'] = 24
if 'sim_start_price' not in st.session_state:
    st.session_state['sim_start_price'] = 1.69

START_DATE = st.sidebar.date_input("Start Date", value=st.session_state['sim_start_date'], min_value=pd.to_datetime("1970-01-01").date(), max_value=pd.to_datetime("today").date(), key="sim_start_date_widget", on_change=lambda: st.session_state.update(sim_start_date=st.session_state.sim_start_date_widget))
# Update main state from widget if changed manually
st.session_state['sim_start_date'] = START_DATE

YEARS = st.sidebar.slider("Duration (Years)", min_value=1, max_value=100, value=st.session_state['sim_years'], key="sim_years_widget", on_change=lambda: st.session_state.update(sim_years=st.session_state.sim_years_widget))
st.session_state['sim_years'] = YEARS



with st.sidebar.expander("Model Coefficients & Lags", expanded=False):
    col_l1, col_k1 = st.columns(2)
    lag1 = col_l1.number_input("Lag 1", min_value=1, max_value=360, value=1)
    k1 = col_k1.slider("k1", min_value=-1.0, max_value=1.0, value=0.50, step=0.01)

    col_l2, col_k2 = st.columns(2)
    lag2 = col_l2.number_input("Lag 2", min_value=1, max_value=360, value=4)
    k2 = col_k2.slider("k2", min_value=-1.0, max_value=1.0, value=-0.25, step=0.01)

    col_l3, col_k3 = st.columns(2)
    lag3 = col_l3.number_input("Lag 3", min_value=1, max_value=360, value=7)
    k3 = col_k3.slider("k3", min_value=-1.0, max_value=1.0, value=0.15, step=0.01)



st.sidebar.subheader("Noise")
vol_mode = st.sidebar.radio("Volatility Mode", ["Auto (% of Price)", "Fixed (Absolute)"], index=0)

target_vol_pct = 0.5
fixed_sigma_input = 0.15

if vol_mode == "Auto (% of Price)":
    target_vol_pct = st.sidebar.slider("Target Daily Volatility %", min_value=0.1, max_value=20.0, value=0.5, step=0.1, help="0.5% is the classic baseline. Increase for meme/penny stocks (e.g. 2-5%).")
else:
    fixed_sigma_input = st.sidebar.slider("Sigma (Absolute Noise)", min_value=0.0, max_value=5.0, value=0.15, step=0.01)

START_PRICE = st.sidebar.number_input("Start Price", min_value=0.01, value=st.session_state['sim_start_price'], step=1.0, key="sim_start_price_widget", on_change=lambda: st.session_state.update(sim_start_price=st.session_state.sim_start_price_widget))
st.session_state['sim_start_price'] = START_PRICE

SEED = st.sidebar.number_input("Random Seed", min_value=0, value=7710, step=1, key="seed_widget")

# Calculate effective sigma
if vol_mode == "Auto (% of Price)":
    sigma = START_PRICE * (target_vol_pct / 100.0)
else:
    sigma = fixed_sigma_input

    
st.sidebar.caption(f"Effective Sigma: {sigma:.4f}")

current_lags = [lag1, lag2, lag3]
current_coeffs = [k1, k2, k3]

# --- Simulation Logic ---


@st.cache_data
def get_market_data(symbol, start_date):
    """Fetches price data for the given symbol from yfinance.
    Returns DataFrame with 'Close' and 'High' columns for accurate max price display.
    """
    import yfinance as yf
    # Add buffer to ensure we cover the start date
    buffer_date = start_date - pd.Timedelta(days=10)

    try:
        # Use Ticker.history() for cleaner data structure
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=buffer_date)
        
        if df.empty:
            return None
            
        # Filter to start exactly on or after start_date
        df.index = df.index.tz_localize(None)  # Remove timezone for compatibility
        df = df[df.index >= pd.Timestamp(start_date)]
        
        # Return DataFrame with Close and High columns
        return df[['Close', 'High']]
    except Exception:
        return None



def run_simulation(start_date, years, seed, lags, coeffs, sigma, start_price=30.0, forced_noise=None):
    """
    Runs the simulation with the given parameters.
    lags: tuple/list of lags (e.g., [1, 4, 7])
    coeffs: tuple/list of coefficients (e.g., [k1, k2, k3])
    forced_noise: optional array of pre-calculated shocks (for Replay Mode)
    """
    np.random.seed(seed)
    N = 250 * years
    
    close = np.zeros(N)
    
    # Initialize based on start_price to match the 'online' snippet logic
    close[0] = start_price
    close[1] = start_price * 1.005
    
    if forced_noise is not None:
        # Use provided noise (truncated/padded to N)
        noise = np.zeros(N)
        limit = min(len(forced_noise), N)
        noise[:limit] = forced_noise[:limit]
        # Valid replay should match N exactly or loop, but zero-pad is safer to avoid drift
    else:
        noise = np.random.normal(0, sigma, size=N)
    
    for t in range(2, N):
        val = 0
        for lag, k in zip(lags, coeffs):
            # Term: k * (close[t-lag] - close[t-(lag+1)])
            if t >= lag + 1:
                val += k * (close[t-lag] - close[t-(lag+1)])
        
        # Original formula: close[t] = close[t-1] + val + noise[t]
        close[t] = close[t-1] + val + noise[t]
        
        # Floor at 0.001 to prevent negative/zero prices but allow penny stocks
        if close[t] < 0.001:
            close[t] = 0.001
            
    dates = pd.date_range(start_date, periods=N, freq="B")
    return dates, close

def run_reverse_simulation(end_date, years, seed, lags, coeffs, sigma, end_price):
    """
    Runs a reverse simulation starting from end_price and moving backwards in time.
    Mechanism is identical to forward simulation but time is inverted.
    """
    np.random.seed(seed + 1) # Use slightly different seed for independence or same? 
    # If mechanism is symmetric, same seed might imply same noise structure? 
    # Let's keep noise independent for now unless specific requirement.
    
    N = 250 * years
    close = np.zeros(N)
    
    # Initialize at the END (index 0 in our reverse array)
    close[0] = end_price
    close[1] = end_price * 0.995 # Reverse of growing 0.5% is shrinking
    
    noise = np.random.normal(0, sigma, size=N)
    
    for t in range(2, N):
        val = 0
        for lag, k in zip(lags, coeffs):
            # Term: k * (close[t-lag] - close[t-(lag+1)])
            # This logic structure holds for "Next Price" generation 
            # In reverse, we are generating "Previous Price" from "Future Prices"
            if t >= lag + 1:
                val += k * (close[t-lag] - close[t-(lag+1)])
        
        close[t] = close[t-1] + val + noise[t]
        if close[t] < 0.001: close[t] = 0.001
            
    # The 'close' array goes from End -> Start. We need to flip it to be Start -> End
    close_forward_order = close[::-1]
    
    # Generate dates (same as forward but we just need the values aligned)
    # We assume N matches the forward simulation exactly
    return close_forward_order

def align_and_compare(sim_dates, sim_close, real_series, metric="Correlation"):
    """
    Aligns simulation and real data on dates and calculates metric.
    """
    # Create DataFrame for simulation
    sim_df = pd.DataFrame({"Sim": sim_close}, index=sim_dates)
    
    # Merge with real data
    # Real data index should be datetime
    combined = pd.concat([sim_df, real_series.rename("Real")], axis=1).dropna()
    
    if len(combined) < 10: 
        return -np.inf if metric == "Correlation" else np.inf
        
    if metric == "Correlation":
        return combined["Sim"].corr(combined["Real"])
    elif metric == "RMSE":
        return np.sqrt(((combined["Sim"] - combined["Real"]) ** 2).mean())
    return 0

def evaluate_seed(seed, start_date, years, lags, coeffs, sigma, real_data, metric_choice, start_price=30.0, sim_mode="Standard (Forward Only)", target_end_price=1.0):
    """
    Worker function to evaluate a single seed.
    """
    np.random.seed(seed)
    N = 250 * years
    close = np.zeros(N)
    
    # Match initialization
    close[0] = start_price
    close[1] = start_price * 1.005
    
    noise = np.random.normal(0, sigma, size=N)
    
    for t in range(2, N):
        val = 0
        for lag, k in zip(lags, coeffs):
            if t >= lag + 1:
                val += k * (close[t-lag] - close[t-(lag+1)])
        close[t] = close[t-1] + val + noise[t]
        if close[t] < 0.001: close[t] = 0.001
            
    # Generate dates
    dates = pd.date_range(start_date, periods=N, freq="B")
    
    # Handle Bidirectional Mode
    if sim_mode == "Bidirectional (Consensus)":
        # We need to run the reverse simulation here as well
        # Note: run_reverse_simulation is now available at module level
        close_fwd = close
        close_rev = run_reverse_simulation(dates[-1], years, seed, lags, coeffs, sigma, target_end_price)
        
        weights = np.linspace(1.0, 0.0, N)
        if len(close_rev) == N:
            close = weights * close_fwd + (1 - weights) * close_rev
        # Fallback to fwd if length mismatch (shouldn't happen)
    
    # Calculate score
    score = align_and_compare(dates, close, real_data, metric_choice)
    return seed, score


# --- Overlay Controls ---
st.sidebar.markdown("---")
st.sidebar.subheader("Overlay Real Data")
show_overlay = st.sidebar.checkbox(f"Overlay Real {target_symbol} Data", value=True)

normalize_prices = False
log_scale_real = True

if show_overlay:
    log_scale_real = st.sidebar.checkbox("Log Scale (Real Data Only)", value=True)
    normalize_prices = st.sidebar.checkbox("Normalize Prices (Start=1.0)", value=False)

# --- Simulation Mode ---
st.sidebar.markdown("---")
st.sidebar.subheader("Simulation Mode")
sim_mode = st.sidebar.radio("Mode", ["Standard (Forward Only)", "Bidirectional (Consensus)", "Forecast (Monte Carlo)"], index=0)

target_end_price = START_PRICE # Default
forecast_days = 20
num_forecast_paths = 50

if sim_mode == "Bidirectional (Consensus)":
    target_end_price = st.sidebar.number_input("Target Final Price", value=START_PRICE, min_value=0.01, key="bidir_target")

if sim_mode == "Forecast (Monte Carlo)":
    st.sidebar.caption("Generate N paths constrained to hit a target price.")
    
    # Try to get current real price first
    _forecast_real_df = get_market_data(target_symbol, pd.Timestamp.today() - pd.Timedelta(days=30))
    _current_real_price = START_PRICE  # Fallback
    if _forecast_real_df is not None and not _forecast_real_df.empty:
        _current_real_price = _forecast_real_df['Close'].iloc[-1]
    
    st.sidebar.metric("Current Price", f"${_current_real_price:.2f}")
    
    forecast_days = st.sidebar.number_input("Forecast Horizon (Days)", min_value=5, max_value=250, value=20)
    target_end_price = st.sidebar.number_input("Target Price at Horizon", value=_current_real_price, min_value=0.01, key="forecast_target")
    num_forecast_paths = st.sidebar.slider("Number of Paths", min_value=10, max_value=200, value=50)

# --- Bidirectional Causality Analysis ---
st.sidebar.markdown("---")
st.sidebar.subheader("Bidirectional Analysis")
enable_bidirectional = st.sidebar.checkbox("Enable Causality Test", value=False)
user_lags = [lag1, lag2, lag3] if 'lag1' in locals() else [1, 4, 7]


# --- Best Seed Search ---
st.sidebar.markdown("---")
st.sidebar.subheader("Best Seed Search")
max_seeds = st.sidebar.number_input("Max Seeds to Scan", min_value=10, max_value=100000, value=10000)

metric_choice = st.sidebar.selectbox("Comparison Metric", ["Correlation", "RMSE"])
compare_log = st.sidebar.checkbox("Compare against Log(Real Price)", value=False, help="Useful for checking shape matches on assets like AAPL over long timeframes.")

if st.sidebar.button("Find Best Seed"):
    real_data_df = get_market_data(target_symbol, START_DATE)
    
    if real_data_df is None or real_data_df.empty:
        st.sidebar.error(f"Could not fetch data for {target_symbol}.")
    else:
        # Use Close column for comparison
        real_data = real_data_df['Close']
        # Apply log transform if requested (for shape matching)
        if compare_log:
            real_data = np.log(real_data)
            
        best_seed = -1
        best_score = -np.inf if metric_choice == "Correlation" else np.inf
        
        progress_bar = st.sidebar.progress(0)
        status_text = st.sidebar.empty()
        
        # Prepare params
        current_lags = [lag1, lag2, lag3]
        current_coeffs = [k1, k2, k3]
        
        # Run parallel search
        with concurrent.futures.ProcessPoolExecutor() as executor:
            # We need to map over seeds
            # Function: evaluate_seed(seed, start_date, years, lags, coeffs, sigma, real_data, metric_choice, start_price, sim_mode, target_end_price)
            
            # Use partial to fix constant arguments
            from functools import partial
            # Note: evaluate_seed must be picklable. It is top level now.
            
            # Pass new args: sim_mode, target_end_price
            worker = partial(evaluate_seed, 
                           start_date=START_DATE, 
                           years=YEARS, 
                           lags=current_lags, 
                           coeffs=current_coeffs, 
                           sigma=sigma, 
                           real_data=real_data, 
                           metric_choice=metric_choice,
                           start_price=START_PRICE,
                           sim_mode=sim_mode,
                           target_end_price=target_end_price)
            
            # Submit tasks
            futures = {executor.submit(worker, seed=s): s for s in range(max_seeds)}
            
            total_seeds = len(futures)
            completed = 0
            
            # Process results as they come in
            for future in concurrent.futures.as_completed(futures):
                seed = futures[future]
                try:
                    s, score = future.result()
                    if metric_choice == "Correlation":
                        if score > best_score:
                            best_score = score
                            best_seed = s
                    else: # RMSE (Lower is better)
                        if score < best_score:
                            best_score = score
                            best_seed = s
                            
                except Exception as exc:
                    pass
                
                completed += 1
                if completed % (total_seeds // 20) == 0:
                     progress_bar.progress(completed / total_seeds)
                     status_text.text(f"Scanning seed {seed}/{max_seeds}... Best: {best_score:.4f}")
        
        progress_bar.progress(1.0)

        status_text.text(f"Found Best Seed: {best_seed}")
        st.sidebar.success(f"Best Seed: {best_seed} ({metric_choice}: {best_score:.4f})")
        st.session_state['suggested_seed'] = best_seed

if 'suggested_seed' in st.session_state:
    st.sidebar.info(f"Last found best seed: {st.session_state['suggested_seed']}")
    
    def apply_seed_callback():
        st.session_state['seed_widget'] = st.session_state['suggested_seed']
        
    st.sidebar.button("Apply Best Fit Seed", on_click=apply_seed_callback)





# Pre-calculation for overlay and analysis
real_subset = None
bidirectional_stats = None

if show_overlay:
    real_data_df = get_market_data(target_symbol, START_DATE)
    if real_data_df is not None and not real_data_df.empty:
        # Use Close for main analysis
        real_data = real_data_df['Close']
        
        # We need dates for masking, but dates are generated by run_simulation?
        # Run simulation once to get dates? Or use START_DATE + YEARS logic.
        # run_simulation depends on forced_noise... chicken and egg.
        # Let's generate dates independently first.
        
        N_pre = 250 * YEARS
        dates_pre = pd.date_range(START_DATE, periods=N_pre, freq="B")
        
        # Filter to simulation range
        real_data.index = pd.to_datetime(real_data.index)
        mask = (real_data.index >= dates_pre[0]) & (real_data.index <= dates_pre[-1])
        real_subset = real_data_df[mask] # Keep DataFrame with High/Close




# --- Advanced Matching ---
st.sidebar.markdown("---")
st.sidebar.subheader("Advanced Matching")
noise_source_mode = st.sidebar.radio("Noise Source", ["Random Generation", "Recovered from Real Data (Analytical)"], index=0)

forced_noise = None

if noise_source_mode == "Recovered from Real Data (Analytical)":
    if show_overlay and real_subset is not None and not real_subset.empty:
        st.sidebar.caption("Solving for exact $\epsilon_t$...")
        
        # Solver Logic
        # Model: Return[t] = Sum(k * (Return[t-lag])) + noise[t]
        # => noise[t] = Return[t] - Sum(...)
        
        prices_solve = real_subset['Close'].values
        log_prices = np.log(prices_solve)
        returns = np.diff(log_prices) # len = N-1
        # Pad returns to match N by prepending 0 (or just handle indexing)
        # Simulation runs for N steps.
        
        # We need to map Real T to Sim T.
        # N = len(dates) which is derived from YEARS.
        # If Real Data << Simulation length, we loop or pad?
        # Ideally we limit Simulation to Real Data length in this mode.
        
        N_sim = 250 * YEARS
        # If real data is shorter, warn.
        if len(returns) < N_sim - 10:
             st.sidebar.warning(f"Real data too short ({len(returns)}) for Sim ({N_sim}). Noise will loop.")
        
        derived_noise = np.zeros(N_sim)
        
        # Calculate AR component
        # Returns[i] corresponds to change P[i] -> P[i+1] (idx relative to diff array)
        # So Return[t] is approx P[t] - P[t-1]
        
        full_returns = np.zeros(N_sim)
        # Fill with actual returns as much as possible
        limit = min(len(returns), N_sim)
        full_returns[:limit] = returns[:limit]
        
        # Solve for Epsilon
        # E[t] = R[t] - Sum(k * (P[t-lag] - P[t-lag-1]))
        # Actually in return space: E[t] = R[t] - Sum(k * R[t-lag])
        # Be careful matching indices.
        # In simulation:
        # val += k * (close[t-lag] - close[t-(lag+1)])
        # This term is exactly k * Return[t-lag] (if using log-approx)
        
        for t in range(2, N_sim):
            pred_return = 0
            for lag, k in zip(user_lags, current_coeffs):
                if t >= lag + 1:
                     # Access past return. 
                     # t is index in 'close'. Return at t-lag is close[t-lag] - close[t-lag-1]
                     # In our full_returns array, index i implies close[i+1]-close[i] ?
                     # No, let's align carefully. 
                     # Sim: close[t] = close[t-1] + val + epsilon[t]
                     # => Return[t] = val + epsilon[t]
                     # val depends on (close[t-lag] - close[t-lag-1]) which is Return[t-lag]
                     
                     prev_ret_idx = t - lag # ?? estimate
                     # If Return[x] = Price[x] - Price[x-1]
                     # Then Price[t-lag] - Price[t-lag-1] is Return[t-lag]
                     
                     if t - lag < len(full_returns) and t-lag >= 0:
                         pred_return += k * full_returns[t-lag]
            
            # True noise = Actual Return - Predicted Return
            if t < len(full_returns):
                derived_noise[t] = full_returns[t] - pred_return
            else:
                 derived_noise[t] = np.random.normal(0, sigma) # Fallback if specific requested
        
        forced_noise = derived_noise
        st.sidebar.success(f"Extracted {len(forced_noise)} shock events.")
        
    else:
        st.sidebar.error("Enable 'Overlay Real Data' to use Recovered Noise.")

# Run Forward Simulation
dates, close_fwd = run_simulation(START_DATE, YEARS, SEED, [lag1, lag2, lag3], [k1, k2, k3], sigma, START_PRICE, forced_noise=forced_noise)
close = close_fwd # Default to forward

if sim_mode == "Bidirectional (Consensus)":
    # Run Reverse Simulation
    close_rev = run_reverse_simulation(dates[-1], YEARS, SEED, [lag1, lag2, lag3], [k1, k2, k3], sigma, target_end_price)
    
    # Blend them: P_consensus = w * P_fwd + (1-w) * P_rev
    # w goes from 1.0 (at start) to 0.0 (at end)
    N = len(close_fwd)
    weights = np.linspace(1.0, 0.0, N)
    
    # We might need to handle length mismatch if run_simulation varies N slightly due to rounding?
    # run_simulation uses N = 250*years. run_reverse uses same. Should coincide.
    if len(close_rev) == N:
        close_consensus = weights * close_fwd + (1 - weights) * close_rev
        close = close_consensus
    else:
        st.error(f"Length mismatch: Fwd {len(close_fwd)} vs Rev {len(close_rev)}")

# --- Forecast Mode (Monte Carlo Ensemble) ---
forecast_paths = []
forecast_dates = None

if sim_mode == "Forecast (Monte Carlo)":
    # Use _current_real_price from UI section
    current_price = _current_real_price if '_current_real_price' in dir() else START_PRICE
        
    # Use today as forecast start
    forecast_start = pd.Timestamp.today().normalize()
    forecast_dates = pd.date_range(forecast_start, periods=forecast_days, freq="B")
    
    for path_seed in range(num_forecast_paths):
        # Forward path
        np.random.seed(SEED + path_seed * 1000)
        fwd_close = np.zeros(forecast_days)
        fwd_close[0] = current_price
        fwd_close[1] = current_price * (1 + np.random.normal(0, sigma / current_price))
        
        noise_fwd = np.random.normal(0, sigma, size=forecast_days)
        
        for t in range(2, forecast_days):
            val = 0
            for lag, k in zip(current_lags, current_coeffs):
                if t >= lag + 1:
                    val += k * (fwd_close[t-lag] - fwd_close[t-(lag+1)])
            fwd_close[t] = fwd_close[t-1] + val + noise_fwd[t]
            if fwd_close[t] < 0.001: fwd_close[t] = 0.001
        
        # Reverse path (from target price)
        np.random.seed(SEED + path_seed * 1000 + 1)
        rev_close = np.zeros(forecast_days)
        rev_close[0] = target_end_price
        rev_close[1] = target_end_price * (1 - np.random.normal(0, sigma / target_end_price))
        
        noise_rev = np.random.normal(0, sigma, size=forecast_days)
        
        for t in range(2, forecast_days):
            val = 0
            for lag, k in zip(current_lags, current_coeffs):
                if t >= lag + 1:
                    val += k * (rev_close[t-lag] - rev_close[t-(lag+1)])
            rev_close[t] = rev_close[t-1] + val + noise_rev[t]
            if rev_close[t] < 0.001: rev_close[t] = 0.001
        
        # Flip reverse to align with time
        rev_close = rev_close[::-1]
        
        # Blend (Consensus)
        weights = np.linspace(1.0, 0.0, forecast_days)
        consensus_path = weights * fwd_close + (1 - weights) * rev_close
        
        forecast_paths.append(consensus_path)




        

if enable_bidirectional and real_subset is not None and not real_subset.empty and len(real_subset) > 50:
    # --- Perform Bidirectional Modeling ---
    # Model: Price_Delta[t] = Sum( Coeff * Price_Delta[t +/- Lag] )
    # We use Log Differences (Returns) for stationarity
    prices = real_subset['Close'].values
    returns = np.diff(np.log(prices))
    n = len(returns)
    
    # Prepare Design Matrices
    # Target y = returns[t]
    # valid range for t: max(lags) to n - max(lags) - 1
    max_lag = max(user_lags)
    valid_idx_start = max_lag
    valid_idx_end = n - max_lag
    
    y = returns[valid_idx_start:valid_idx_end]
    
    # Forward Matrix X_fwd: returns[t-L]
    X_fwd = np.zeros((len(y), len(user_lags)))
    for i, lag in enumerate(user_lags):
        # if y[0] is at index `valid_idx_start`, then lag is `valid_idx_start - lag`
        # returns is 0-indexed. 
        # y corresponds to indices [valid_idx_start ... valid_idx_end-1]
        # X column for lag L: indices [valid_idx_start-L ... valid_idx_end-1-L]
        X_fwd[:, i] = returns[valid_idx_start-lag : valid_idx_end-lag]
        
    # Reverse Matrix X_rev: returns[t+L]
    X_rev = np.zeros((len(y), len(user_lags)))
    for i, lag in enumerate(user_lags):
        # X column for future lag L: indices [valid_idx_start+L ... valid_idx_end-1+L]
        X_rev[:, i] = returns[valid_idx_start+lag : valid_idx_end+lag]
        
    # Fit Models (OLS)
    # coefs = (X.T X)^-1 X.T y
    coeffs_fwd, resid_fwd, rank_fwd, s_fwd = np.linalg.lstsq(X_fwd, y, rcond=None)
    coeffs_rev, resid_rev, rank_rev, s_rev = np.linalg.lstsq(X_rev, y, rcond=None)
    
    # Calculate R2
    sst = np.sum((y - np.mean(y))**2)
    sse_fwd = resid_fwd[0] if len(resid_fwd) > 0 else np.sum((y - X_fwd @ coeffs_fwd)**2)
    sse_rev = resid_rev[0] if len(resid_rev) > 0 else np.sum((y - X_rev @ coeffs_rev)**2)
    
    r2_fwd = 1 - (sse_fwd / sst)
    r2_rev = 1 - (sse_rev / sst)
    
    bidirectional_stats = {
                "r2_fwd": r2_fwd, "r2_rev": r2_rev,
                "coeffs_fwd": coeffs_fwd, "coeffs_rev": coeffs_rev,
                "lags": user_lags
            }


# Apply Normalization to Simulation
sim_plot_data = close.copy()
sim_label = "Simulated Price"
if normalize_prices:
    sim_plot_data = close / close[0]
    sim_label += " (Norm=1.0)"

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [2, 1]})

# Plot Simulation on Primary Axis (Linear)
ax1.plot(dates, sim_plot_data, linewidth=1, label=sim_label, color='tab:blue')
ax1.set_ylabel("Simulated Price", color='tab:blue')

# Plot Forecast Ensemble if active
if sim_mode == "Forecast (Monte Carlo)" and len(forecast_paths) > 0:
    # Plot each path with low alpha
    for path in forecast_paths:
        ax1.plot(forecast_dates, path, linewidth=0.5, alpha=0.15, color='tab:green')
    
    # Calculate and plot percentile bands
    paths_arr = np.array(forecast_paths)
    p10 = np.percentile(paths_arr, 10, axis=0)
    p50 = np.percentile(paths_arr, 50, axis=0)
    p90 = np.percentile(paths_arr, 90, axis=0)
    
    ax1.fill_between(forecast_dates, p10, p90, alpha=0.3, color='tab:green', label="Forecast 10-90% Range")
    ax1.plot(forecast_dates, p50, linewidth=2, color='tab:green', label=f"Forecast Median (Target: ${target_end_price:.2f})")
    
    # Mark target price
    ax1.axhline(target_end_price, color='green', linestyle='--', alpha=0.7, linewidth=1)

# Plot Real Data Overlay
if show_overlay and real_subset is not None and not real_subset.empty:
    ax1_twin = ax1.twinx()
    plot_values = real_subset['Close'].values
    high_values = real_subset['High'].values
    label_suffix = ""
    
    if normalize_prices:
        norm_factor = plot_values[0]
        plot_values = plot_values / norm_factor
        high_values = high_values / norm_factor
        label_suffix = " (Norm=1.0)"

    real_label = f"Real {target_symbol}{label_suffix}"
    if log_scale_real:
        real_label += " (Log)"
        
    ax1_twin.plot(real_subset.index, plot_values, linewidth=1, color='orange', alpha=0.8, label=real_label)
    ax1_twin.set_ylabel("Real Price (Split-Adj)", color='orange')
    ax1_twin.tick_params(axis='y', labelcolor='orange')
    
    if log_scale_real:
        ax1_twin.set_yscale('log')
        from matplotlib.ticker import ScalarFormatter
        ax1_twin.yaxis.set_major_formatter(ScalarFormatter())
    
    # Mark Max Price
    real_max_val = np.max(high_values)
    ax1_twin.axhline(real_max_val, color='orange', linestyle='--', alpha=0.5, linewidth=0.8)
    
    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1_twin.get_legend_handles_labels()
    ax1_twin.legend(lines1 + lines2, labels1 + labels2, loc='upper left', framealpha=1.0, facecolor='white').set_zorder(100)
else:
    ax1.legend(loc='upper left', framealpha=1.0, facecolor='white')

ax1.set_title(f"Simulated vs Real Price Action")


# Bidirectional Visual Analysis
if enable_bidirectional and bidirectional_stats:
    ax2.set_title("Bidirectional Model Coefficients (Forward vs Reverse Causality)")
    lags = bidirectional_stats['lags']
    x = np.arange(len(lags))
    width = 0.35
    
    rects1 = ax2.bar(x - width/2, bidirectional_stats['coeffs_fwd'], width, label='Forward (Past Lags)', color='tab:blue', alpha=0.7)
    rects2 = ax2.bar(x + width/2, bidirectional_stats['coeffs_rev'], width, label='Reverse (Future Lags)', color='tab:purple', alpha=0.7)
    
    ax2.set_ylabel('Coefficient Magnitude')
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"Lag {l}" for l in lags])
    ax2.legend()
    ax2.axhline(0, color='black', linewidth=0.5)
    
    # Annotate stats
    info_text = (f"Forward R²: {bidirectional_stats['r2_fwd']:.4f}\n"
                 f"Reverse R²: {bidirectional_stats['r2_rev']:.4f}\n"
                 f"Symmetry Score: {bidirectional_stats['r2_rev'] / bidirectional_stats['r2_fwd']:.2f}")
    ax2.text(0.02, 0.95, info_text, transform=ax2.transAxes, verticalalignment='top', 
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
else:
    ax2.text(0.5, 0.5, "Enable 'Causality Test' to view Forward vs Reverse Model comparison", ha='center', va='center')
    ax2.axis('off') # Hide axes if not active


    




ax1.set_title(f"{YEARS}-year Simulation (Lags: {current_lags}, Coeffs: {current_coeffs})")
ax1.xaxis.set_major_locator(mdates.YearLocator(base=max(1, YEARS // 6))) # Adaptive locator

ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
ax1.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()

st.pyplot(fig)


# --- Metrics ---
# --- Metrics ---

# --- Statistics ---
st.write("### Simulation Statistics")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Start Price", f"{sim_plot_data[0]:.2f}")
col2.metric("Final Price", f"{sim_plot_data[-1]:.2f}")
col3.metric("Max Price", f"{np.max(sim_plot_data):.2f}")
col4.metric("Min Price", f"{np.min(sim_plot_data):.2f}")

if show_overlay and real_subset is not None and not real_subset.empty:
    st.write(f"### Real {target_symbol} Statistics")
    
    # Calculate Symmetry Score if Mirror Mode active
    # Calculate Symmetry Score if Bidirectional Mode active
    sym_score_display = "N/A"
    
    if enable_bidirectional and bidirectional_stats:
        ratio = bidirectional_stats['r2_rev'] / bidirectional_stats['r2_fwd']
        sym_score_display = f"{ratio:.4f}"
    
    r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns(5)
    r_col1.metric("Real Start", f"{real_subset['Close'].iloc[0]:.2f}")
    r_col2.metric("Real Final", f"{real_subset['Close'].iloc[-1]:.2f}")
    r_col3.metric("Real Max (High)", f"{real_subset['High'].max():.2f}")
    r_col4.metric("Real Min", f"{real_subset['Close'].min():.2f}")
    r_col5.metric("Symmetry Score", sym_score_display, help="Correlation between Forward and Reversed price history. Higher = more palindromic.")



# --- Data View ---
with st.expander("View Raw Data"):
    df = pd.DataFrame({"Date": dates, "Sim_Close": close})
    
    if show_overlay and real_subset is not None and not real_subset.empty:
        # Reindex real data to simulation dates for table alignment
        real_df = pd.DataFrame({"Real_Close": real_subset['Close']})
        # Merge on Date (which is index of real_subset)
        # Let's just create a combined dataframe on the Sim Index
        df = df.set_index("Date")
        combined_view = df.join(real_df, how="left")
        st.dataframe(combined_view)
    else:
        st.dataframe(df)

