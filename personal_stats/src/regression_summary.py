def print_regression_summary(X, y, model=None, feature_names=None):
    """
    Prints a detailed regression summary similar to R/Stata output
    
    Parameters:
    -----------
    X : array-like of shape (n_samples, n_features)
        Training data
    y : array-like of shape (n_samples,)
        Target values
    model : fitted sklearn model, optional
        If None, creates new LinearRegression
    feature_names : list-like, optional
        Names of features. If None, uses X.columns if available
    """
    if model is None:
        model = LinearRegression()
        model.fit(X, y)
    
    # Get feature names
    if feature_names is None:
        feature_names = getattr(X, 'columns', [f'X{i}' for i in range(X.shape[1])])
    
    # Calculate standard errors and t-statistics
    n = X.shape[0]
    p = X.shape[1]
    
    # Calculate residuals and MSE
    y_pred = model.predict(X)
    residuals = y - y_pred
    mse = np.sum(residuals**2) / (n - p - 1)
    
    # Calculate variance-covariance matrix
    X_array = np.array(X)
    var_covar_matrix = mse * np.linalg.inv(X_array.T.dot(X_array))
    
    # Standard errors are sqrt of diagonal elements
    std_errors = np.sqrt(np.diag(var_covar_matrix))
    
    # Calculate t-statistics and p-values
    t_stats = model.coef_ / std_errors
    p_values = 2 * (1 - stats.t.cdf(abs(t_stats), n - p - 1))
    
    # Calculate R-squared and adjusted R-squared
    r2 = model.score(X, y)
    adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1)
    
    # Calculate F-statistic
    f_stat = (r2 / p) / ((1 - r2) / (n - p - 1))
    f_p_value = 1 - stats.f.cdf(f_stat, p, n - p - 1)
    
    # Print summary
    print('='*80)
    print('                              Regression Results                              ')
    print('='*80)
    print(f'Number of Observations:     {n}')
    print(f'Degrees of Freedom:         {n - p - 1}')
    print(f'R-squared:                  {r2:.4f}')
    print(f'Adjusted R-squared:         {adj_r2:.4f}')
    print(f'F-statistic:               {f_stat:.4f}')
    print(f'Prob (F-statistic):        {f_p_value:.4f}')
    print('-'*80)
    print('                    coef    std err    t-stat    P>|t|    [95% Conf. Int.]')
    print('-'*80)
    
    # Print coefficient table
    for i, name in enumerate(feature_names):
        conf_int = stats.t.interval(0.95, n - p - 1, 
                                  loc=model.coef_[i], 
                                  scale=std_errors[i])
        print(f'{name[:20]:20} {model.coef_[i]:>9.4f} {std_errors[i]:>10.4f} ',
              f'{t_stats[i]:>9.4f} {p_values[i]:>9.4f} ',
              f'[{conf_int[0]:>7.4f}, {conf_int[1]:>7.4f}]')
    
    # Print intercept
    if hasattr(model, 'intercept_'):
        print('-'*80)
        print(f'Intercept: {model.intercept_:.4f}')
    print('='*80)
    
    return {
        'r2': r2,
        'adj_r2': adj_r2,
        'f_stat': f_stat,
        'f_p_value': f_p_value,
        'coefficients': model.coef_,
        'std_errors': std_errors,
        't_stats': t_stats,
        'p_values': p_values
    }