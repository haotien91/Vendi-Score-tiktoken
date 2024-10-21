## This repo is modified from ![Vendi-Score](https://github.com/vertaix/Vendi-Score)

For using this repository, please follow the steps below:
1. Create a new conda env
```bash
conda create -n vendi-score python=3.10 -y
```

2. install the requirements package
```bash
pip install -r requirements
```

3. install the Vendi-Score package
```bash
cd Vendi-Score
pip install -e .
```

4. Back to example directory, try it!
```bash
cd ../example
python text_embedding.py
```